import asyncio,json
from pathlib import Path
from websockets.asyncio.client import connect
TOKEN=(Path(__file__).resolve().parents[1]/'.build/local-token').read_text().strip()
async def main():
    async with connect('ws://127.0.0.1:8765') as a:
        await a.send(json.dumps({'token':TOKEN}));assert json.loads(await a.recv())['type']=='ready'
        async with connect('ws://127.0.0.1:8765') as b:
            await b.send(json.dumps({'token':TOKEN}));assert json.loads(await b.recv())['type']=='error'
        await a.send(b'bad frame');assert json.loads(await a.recv())['type']=='error'
    print('Concurrent-client and malformed-PCM rejection passed')
if __name__=='__main__':asyncio.run(main())
