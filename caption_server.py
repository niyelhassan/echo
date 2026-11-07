"""Loopback-only authenticated server. Offline by default; --download warms caches."""
import argparse
import asyncio
import hmac
import json
import logging
from pathlib import Path
import secrets
import numpy as np
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from local_engine import LocalModels, Session
from sound_events import REPO as SOUND_REPO

ROOT = Path(__file__).resolve().parent

async def run(args):
    token_file = ROOT/'.build/local-token'
    token_file.parent.mkdir(exist_ok=True)
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32))
    token_file.chmod(0o600)
    token = token_file.read_text().strip()
    print('Loading local models…', flush=True)
    models = LocalModels(download=args.download)
    # Warm every model before admitting clients so the first caption is not delayed by compilation.
    await asyncio.to_thread(models.warm)
    busy = False

    async def handler(ws):
        nonlocal busy
        origin = ws.request.headers.get('Origin', '')
        # Browser websites cannot authenticate or feed audio; Python test clients have no Origin.
        if origin and not origin.startswith('chrome-extension://'):
            await ws.close(1008, 'Only the paired extension can connect'); return
        session = None
        acquired = False
        async def send(event): await ws.send(json.dumps(event))
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if not isinstance(hello,dict) or not hmac.compare_digest(str(hello.get('token','')),token):
                await ws.close(1008, 'Invalid pairing token'); return
            # A restart can arrive while the previous session is still finishing its in-flight inference.
            for _ in range(30):
                if not busy: break
                await asyncio.sleep(.1)
            if busy:
                await send({'type':'error','message':'Another tab is already connected. Stop it first.'}); return
            busy = acquired = True
            session = Session(models, send)
            await send({'type':'ready','sample_rate':16000,'packet_samples':1600,
                        'models':{'captions':LocalModels.ASR,'tone':LocalModels.TONE,'sounds':SOUND_REPO}})
            async for message in ws:
                if isinstance(message,bytes):
                    if len(message) != 6400: raise ValueError('Expected 100 ms / 1600 float32 samples')
                    audio = np.frombuffer(message,dtype='<f4').copy()
                    if not np.isfinite(audio).all() or np.max(np.abs(audio)) > 1.01: raise ValueError('Invalid PCM samples')
                    await session.feed(audio)
                else:
                    command = json.loads(message)
                    if command.get('type') == 'flush':
                        await session.flush()
                        await send({'type':'flushed'})
                    elif command.get('type') == 'stop':
                        await session.flush(); break
                    else: raise ValueError('Unknown command')
        except ConnectionClosed:
            pass
        except Exception as exc:
            try: await send({'type':'error','message':str(exc)})
            except ConnectionClosed: pass
        finally:
            if session: await session.close()
            if acquired: busy = False

    async with serve(handler,'127.0.0.1',8765,max_size=8192,max_queue=4,compression=None):
        print(f'Ready: ws://127.0.0.1:8765\nPairing token: {token}\nAudio stays local. Ctrl-C stops the service.',flush=True)
        await asyncio.Future()

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--download',action='store_true',help='Allow first-run model downloads')
    try: asyncio.run(run(parser.parse_args()))
    except KeyboardInterrupt: pass
