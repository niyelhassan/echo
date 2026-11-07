#!/bin/zsh
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
uv run python caption_server.py "$@"
