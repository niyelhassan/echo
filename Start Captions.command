#!/bin/zsh
cd -- "${0:A:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
echo 'Tonal — local system-audio transcription'
echo 'Play a video or meeting. Captions arrive approximately every five seconds.'
echo 'Emotion and sarcasm labels are not available in this prototype yet.'
echo 'Press Control-C to stop.'
mkdir -p .build
uv run python capture.py --system --pretty 2> >(tee .build/startup.log >&2)
echo 'Caption session ended. You may close this window.'
read -r '?Press Return to close.'
