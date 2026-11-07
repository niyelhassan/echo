#!/bin/zsh
# One-time setup: Python dependencies, local model download (~3 GB), and the Chrome launcher.
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
if ! command -v uv >/dev/null; then
  echo "Installing uv (Python package manager)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v ffmpeg >/dev/null || echo "Note: ffmpeg is only needed for the test scripts (brew install ffmpeg)."
uv sync --frozen && uv run python install.py
echo
echo "Done. In Chrome: chrome://extensions → Developer mode → Load unpacked → choose the 'extension' folder."
read -k1 "?Press any key to close."
