# Echo — live, on-device captions with sound cues and tone

Private, on-device live captions for any Chrome tab, built for deaf and hard-of-hearing viewers. Echo shows what was said, the sounds around it (`[laughter]`, `[applause]`, `[♪ music ♪]`, `[crying]`), and a tentative vocal tone (`[sounds angry]`). No audio leaves the Mac.

## How it works

- **Chrome extension (Manifest V3).** Captures the selected tab's audio through `tabCapture` in an offscreen document, while keeping normal playback. It renders an overlay that is minimal, draggable, and works in fullscreen, plus a searchable transcript you can copy or save.
- **Local service (Python, Apple Silicon).** An authenticated loopback WebSocket feeds three independent workers:
  - captions: NVIDIA Parakeet TDT 0.6B v2 via MLX, with Silero VAD segmentation;
  - sound cues: CED-base AudioSet tagger on rolling 3 s windows;
  - vocal tone: emotion2vec+ base. It never delays captions.
- **Native Messaging launcher.** Clicking **Start captions** starts the service and pairs automatically.

## Setup (Apple Silicon Mac)

1. Double-click **Install Tone Caption.command**. Alternatively, run `uv sync && uv run python install.py`, which downloads about 3 GB of models and registers the launcher with Chrome.
2. In `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the `extension` folder. The extension ID must be `pnangodkiechjldahinmjhkmkoaideib`.
3. On any tab, click the extension and then **Start captions**, or press **Alt+Shift+C**. **Alt+Shift+T** toggles the transcript.

## Measured results (7 Nov 2026, M3 Pro)

- **Captions:** 10.6% word error rate against human captions on TED talks, stand-up comedy, a film argument, and a sitcom sketch (Parakeet). Whisper base.en scored 14.4% and Whisper large-v3-turbo 9.2%, but turbo took about 7× longer.
- **Laughter cues:** on held-out videos, 6 of 9 human-annotated laughs were cued.
- **Tone:** thresholds are conservative hand-set values. Tone labels are estimates, often wrong, and never detect sarcasm.

`benchmark_real_asr.py`, `evaluate_sounds.py`, `tests/browser_real.py`, and `tests/browser_youtube.py` reproduce these measurements. `VALIDATION.md` contains earlier acted-speech results.

## Tests

```sh
uv run python -m unittest discover -s tests -p test_engine.py
uv run python tests/browser_youtube.py <youtube-id> 90
```
