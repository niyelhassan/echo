"""Paced real-video audio through the actual authenticated WebSocket service."""
import asyncio,json,subprocess,time,sys
from pathlib import Path
import numpy as np
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
ROOT=Path(__file__).resolve().parents[1]
TOKEN=(ROOT/'.build/local-token').read_text().strip()

async def replay(name,audio):
    events=[]
    async with connect('ws://127.0.0.1:8765') as ws:
        await ws.send(json.dumps({'token':TOKEN}))
        assert json.loads(await ws.recv())['type']=='ready'
        started=time.perf_counter()
        async def receive():
            async for raw in ws:
                e=json.loads(raw);e['wall_seconds']=time.perf_counter()-started;events.append(e)
                if e['type']=='error':raise AssertionError(e)
                if e['type']=='flushed':return
        receiver=asyncio.create_task(receive())
        padded=np.pad(audio,(0,(-len(audio))%1600))
        for i in range(0,len(padded),1600):
            await ws.send(padded[i:i+1600].astype('<f4').tobytes())
            await asyncio.sleep(max(0,started+(i+1600)/16000-time.perf_counter()))
        await ws.send(json.dumps({'type':'flush'}))
        await asyncio.wait_for(receiver,20)
    await asyncio.sleep(.2)
    finals=[e for e in events if e.get('final') and e.get('channel')=='text']
    if name in ('silence','noise','sine'):assert not finals,finals
    else:assert any(e.get('text') for e in finals),events
    return {'name':name,'duration':len(audio)/16000,'events':events}

async def main():
    checks=[]
    for kwargs,hello in [({}, {'token':'wrong'}),({'origin':'https://example.com'},{'token':TOKEN})]:
        async with connect('ws://127.0.0.1:8765',**kwargs) as ws:
            try:
                await ws.send(json.dumps(hello));await ws.recv();raise AssertionError('Unauthorized connection accepted')
            except ConnectionClosed as e:assert e.rcvd.code==1008
        checks.append('rejected unauthorized client')
    results=[await replay('silence',np.zeros(32000,np.float32))]
    cases=[] if '--nonspeech' in sys.argv else [('expressive-video',ROOT/'.build/emotion-demo/expressive-speech.mp4')]
    if '--nonspeech' in sys.argv:
        results.append(await replay('noise',np.random.default_rng(7).normal(0,.02,32000).astype(np.float32)))
        results.append(await replay('sine',(np.sin(np.arange(32000)*2*np.pi*440/16000)*.1).astype(np.float32)))
    for name,file in cases:
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(file),'-vn','-ac','1','-ar','16000','-f','f32le','pipe:1'])
        audio=np.concatenate((np.frombuffer(raw,dtype='<f4'),np.zeros(8000,np.float32)))
        results.append(await replay(name,audio))
    (ROOT/('.build/evaluation/nonspeech.json' if '--nonspeech' in sys.argv else '.build/evaluation/stream.json')).write_text(json.dumps({'checks':checks,'results':results},indent=2))
    for r in results:
        captions=[e for e in r['events'] if e.get('type')=='caption']
        print(r['name'],'events',len(captions),'p95 processing ms',np.percentile([e['queue_and_processing_ms'] for e in captions],95) if captions else 0)
        for e in captions:
            if e['final']:print(e.get('text') or e.get('tone',{}).get('label'))

if __name__=='__main__':asyncio.run(main())
