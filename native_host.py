"""Chrome Native Messaging host: starts the loopback caption service on demand and returns its token.

Chrome launches this process only for the extension ID listed in the installed host manifest.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN = ROOT/'.build/local-token'
LOG = ROOT/'.build/server.log'
PORT = 8765
STARTUP_TIMEOUT = 120


def read():
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    return json.loads(sys.stdin.buffer.read(struct.unpack('<I', header)[0]))


def write(message):
    data = json.dumps(message).encode()
    sys.stdout.buffer.write(struct.pack('<I', len(data)) + data)
    sys.stdout.buffer.flush()


def listening():
    with socket.socket() as s:
        s.settimeout(.3)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def ready_in_log():
    return LOG.exists() and 'Ready: ws://127.0.0.1' in LOG.read_text(errors='ignore')[-4000:]


def ensure():
    if listening():
        return {'ok': True, 'token': TOKEN.read_text().strip(), 'started': False}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, 'w') as log:
        subprocess.Popen([str(ROOT/'.venv/bin/python'), str(ROOT/'caption_server.py')], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                         env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if listening() and ready_in_log():
            return {'ok': True, 'token': TOKEN.read_text().strip(), 'started': True}
        if LOG.exists() and 'Traceback' in LOG.read_text(errors='ignore'):
            return {'ok': False, 'error': 'The local caption service failed to start. See .build/server.log.'}
        time.sleep(.25)
    return {'ok': False, 'error': 'The local caption service took too long to load its models.'}


def main():
    message = read()
    if not message:
        return
    try:
        if message.get('type') == 'ensure':
            write(ensure())
        elif message.get('type') == 'status':
            write({'ok': True, 'running': listening()})
        else:
            write({'ok': False, 'error': 'Unknown request'})
    except Exception as exc:
        write({'ok': False, 'error': str(exc)})


if __name__ == '__main__':
    main()
