# Tone Caption: Chrome extension + fully local service

The implemented version targets **Apple Silicon macOS** (tested on an M3 Pro), Chrome 116+, and English audio. The extension captures the tab you select and overlays revisable captions with tentative vocal tone labels. The companion service runs MLX Whisper base.en, emotion2vec+ base, and Silero VAD on your Mac. No OpenRouter key or cloud inference is used.

## Start on this Mac

1. Double-click **Start Local Service.command** in this folder. Leave the terminal open. Wait for “Ready” and copy its pairing token. If a service is already running on port 8765, use that instance or stop it with Ctrl-C first.
2. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select this project's **extension** folder.
3. Open a normal webpage with audio/video. Click the Tone Caption extension, paste the token once, and click **Caption this tab**. Start playback.
4. Use **Stop captions**, or the overlay's ×, to stop. Navigating or closing the captured tab stops capture. Start again on the next page.

The token is saved in extension-local storage, not synced. Its service copy is `.build/local-token` (owner-readable only). Audio is buffered in RAM, not recorded. No microphone permission is requested. Capturing a tab preserves its audible playback. Only one tab can be processed at a time.

## First-time installation on another Apple Silicon Mac

Install Python tooling (`uv`) and FFmpeg, then in this project:

```sh
uv sync --frozen
uv run python caption_server.py --download
```

`--download` permits downloading the model weights on first run. Subsequent starts use:

```sh
uv run python caption_server.py
```

Normal starts use local model directories, `local_files_only=True`, `HF_HUB_OFFLINE=1`, and `TRANSFORMERS_OFFLINE=1`. Internet is required for initial dependency/model downloads, not caption inference. Websites playing online videos naturally still need their own connection. The service binds only to `127.0.0.1:8765`; the extension's connection policy allows that WebSocket endpoint only. No external script or model is loaded by the extension.

## What to expect

- First partial captions after roughly one second of speech plus processing; the measured second browser video produced its first text 1.41 seconds after playback began (including source silence).
- Revisions about every 600 ms; finalization after about 400 ms of silence or a six-second utterance cap.
- Captions and tone run independently. The overlay's processing number excludes the time needed to gather speech. It is **not total caption delay**.
- Tone is an estimate of vocal expression, not a statement about the person's feelings. Labels remain “Possibly …”; weak scores show “Uncertain / mixed.” Scores are not calibrated probabilities.
- Captions can revise or contain mistakes. Short utterances, continuous speech split at the six-second cap, music, overlap, accents, and dramatic editing can reduce accuracy. There is no speaker diarization or sarcasm detector.
- Fullscreen works for ordinary HTML fullscreen containers. Picture-in-picture, browser-owned pages, the Chrome Web Store, DRM-protected media, and third-party cross-origin fullscreen players are not verified. Cross-origin iframe fullscreen may hide the top-frame overlay.
- Starting capture partway through a sentence can lose its beginning. Seeking while capturing may temporarily combine unrelated speech; stop/restart to clear context.
- Stopping removes the overlay immediately and discards the remaining partial utterance. Nothing is exported or saved.
- Windows/Linux and browser-only WebGPU inference are not implemented in this build.

## Test and reproduce

With the service running, execute these sequentially (one capture client at a time):

```sh
uv run python -m unittest discover -s tests -p test_engine.py -v
uv run python tests/test_protocol.py
uv run python tests/test_stream.py
uv run python tests/test_stream.py --nonspeech
uv run python tests/browser_smoke.py
uv run python tests/browser_smoke.py --heldout
```

Browser tests use an isolated Chromium profile in `.build/browser-test-profile`, not your personal Chrome profile. Install the test browser if needed with `uv run playwright install chromium`. Prepare downloaded videos with `prepare_demo.py` and `prepare_browser_cases.py`. `tests/video.html` is a local video test fixture, not a hosted product.

See **VALIDATION.md** for measurements, model comparisons, and accuracy limits. Existing native Swift/system-audio prototypes are separate tools; this extension uses the new streaming service.
