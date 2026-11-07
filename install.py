"""One-time setup: download models, and register the native host with Chrome-family browsers.

Usage: uv run python install.py [--profile DIR]   (--profile also registers a custom --user-data-dir)
"""
import argparse
import json
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = 'com.tonecaption.service'
EXTENSION_ID = 'pnangodkiechjldahinmjhkmkoaideib'
SUPPORT = Path.home()/'Library/Application Support'
BROWSERS = ['Google/Chrome', 'Google/Chrome Beta', 'Google/Chrome Canary', 'Chromium',
            'BraveSoftware/Brave-Browser', 'Microsoft Edge', 'Arc/User Data']


def register(directories):
    launcher = ROOT/'native_host.sh'
    launcher.write_text(f'#!/bin/zsh\nexec "{ROOT}/.venv/bin/python" "{ROOT}/native_host.py" "$@"\n')
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    manifest = {'name': HOST, 'description': 'Tonal local service launcher', 'path': str(launcher),
                'type': 'stdio', 'allowed_origins': [f'chrome-extension://{EXTENSION_ID}/']}
    written = []
    for directory in directories:
        target = directory/'NativeMessagingHosts'
        target.mkdir(parents=True, exist_ok=True)
        (target/f'{HOST}.json').write_text(json.dumps(manifest, indent=2))
        written.append(target/f'{HOST}.json')
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, action='append', default=[])
    parser.add_argument('--skip-models', action='store_true')
    args = parser.parse_args()
    if not args.skip_models:
        print('Downloading and warming local models (first run only)…', flush=True)
        from local_engine import LocalModels
        LocalModels(download=True).warm()
    browsers = [SUPPORT/b for b in BROWSERS if (SUPPORT/b).exists()]
    for path in register(browsers + [p.resolve() for p in args.profile]):
        print('Registered', path)
    print(f'Load the "extension" folder in chrome://extensions (Developer mode → Load unpacked).'
          f'\nIts ID should be {EXTENSION_ID}.')


if __name__ == '__main__':
    main()
