# Validation and model decision — 7 November 2026

## Decision

Use **MLX Whisper base.en + emotion2vec+ base + Silero VAD** on this Apple M3 Pro. Chrome captures 100 ms packets through an offscreen document and AudioWorklet; its AudioContext resamples to mono 16 kHz. An authenticated loopback WebSocket feeds independent caption and tone workers. Bounded queues coalesce obsolete partial revisions and explicitly fail if processing cannot keep up.

The local Python service is part of the product. “Fully local” does not mean “all inside Chrome.” Cached inference runs offline; setup downloads dependencies and weights.

## Models considered and measured

| Option | Evidence and decision |
| --- | --- |
| NVIDIA Audio2Emotion v2.2 | Not integrated: its published terms restrict use to Audio2Face and prohibit standalone emotion recognition. This is not a license fit for the requested caption indicator. |
| emotion2vec+ base | Selected. About 90M parameters. 19/27 (70.4%) audio-majority matches on the fixed test sample; median 102 ms tone inference. |
| emotion2vec+ large | Tested on development clips: 59.3% vs base's 63.0%; median 141 ms vs 97 ms. No measured benefit for this application sample. Not run on the test split after development rejection. |
| Existing Wav2Vec2 classifier | 10/27 (37.0%) test matches; frequent happy/neutral → angry confusions. Replaced in the extension. |
| SenseVoiceSmall, joint transcription + emotion | Tested on all 64 clips. Default configuration predominantly emitted EMO_UNKNOWN. Also tested documented implementation option `ban_emo_unk=True`: 16/27 (59.3%) test matches, 2.5% word error rate, median 689 ms joint inference on CPU. Better transcription on this tiny repeated-phrase set, but slower and less accurate for tone than the selected combination. Forcing an emotion also removes its useful unknown escape. Benchmark adapter is retained in evaluate_sensevoice.py; not the extension default. |
| MLX Whisper base.en | Selected for English captions: 3.75% WER on 32 test clips, warmed median 55 ms, p95 58 ms for complete-clip inference. Development WER 7.5%. |
| MLX Whisper small | Development WER 8.125%, median 162 ms. Not selected over base.en based on this sample. |
| whisper.cpp / faster-whisper | Reasonable portable/native or CUDA alternatives; researched, not benchmarked or integrated here. |
| sherpa-onnx streaming recognizers | A candidate if tighter incremental word latency or portable ONNX deployment is the main requirement. Researched, not benchmarked or integrated; needs separate tone model and accuracy testing. |

These comparisons are machine- and sample-specific, not universal model rankings. SenseVoice ran on CPU with four Torch threads; MLX uses Apple acceleration. Timing runs were not all under identical machine load.

## Accuracy method and its limits

`prepare_evaluation.py` fixes 64 CREMA-D clips: eight actors, two phrases (DFA/IWW), four intended expressions. Actors 1001–1004 form development; 1005–1008 form the test subset. The reference is **audio-only human majority vote**, not the actor's intended emotion or filename. Five clips per split have tied votes and are excluded from top-label accuracy. No label enters inference.

This speaker separation concerns our evaluation/tuning only. CREMA-D may overlap pretraining or fine-tuning data of these pretrained models; this is not a contamination-free generalization benchmark. Only two repeated phrases are transcribed. The sample is too small and too narrow to certify everyday web video accuracy.

All 27 unambiguous test clips passed emotion2vec's existing score/margin threshold, including eight wrong labels. Therefore its confidence threshold is not a demonstrated accuracy guarantee. UI wording remains tentative. Neutral/happy/sad distinctions are still imperfect. Do not interpret the model score as a calibrated probability. No claim is made that labels are always correct, or that sarcasm, real internal emotion, multiple speakers, fear, or disgust are reliably identified.

## End-to-end tests

- Paced audio decoded from the real expressive video, sent over the actual WebSocket: 40 caption/tone events, p95 queue-plus-inference 155 ms. Captions contained errors such as “Don't forget to jack it”; the tests did not hide these.
- Actual Chromium tabCapture, offscreen document, AudioWorklet, local models, and on-page overlay exercised on two video montages: eight clips from actors 1001/1002, and four IWW clips from actors 1005/1006. Video/audio data were not replaced by mock model results.
- Final first-montage run (after preserving full-bandwidth audio playback): first text at 1.571 s after play; 40 inference events; p95 queue-plus-inference 182 ms. Fullscreen, stopping, restarting, and navigation cleanup passed, with no page JavaScript errors.
- Second montage: first nonempty caption arrived **1.411 s after video play**; p95 queue-plus-inference **128 ms**, 30 inference events. Fullscreen, stop, restart and navigation passed after fixing a race where a delayed fullscreen event could restore a stopped overlay.
- Silence, seeded white noise, and a 440 Hz tone each produced zero caption/tone events in paced WebSocket tests.
- Unit tests cover sustained silence, bounded six-second utterances, partial/final ordering, and independent final worker results.
- Unauthorized tokens and browser website origins are rejected. Concurrent clients and malformed PCM were also rejected in passing protocol tests.

The processing figures exclude initial audio collection, browser packetization, and model loading. A first partial requires about one second of audio; finalization normally adds 400 ms of silence. The displayed processing number is deliberately labeled as processing, not end-to-end lag. Browser video tests are functional/latency checks; the complete-clip model accuracy table is a separate measurement and must not be read as live-overlay accuracy.

Raw records: `.build/evaluation/{candidate-base-test-cpu-4,baseline-base-test-cpu-4,asr-base.en-test,sensevoice,sensevoice-forced,stream,browser-expressive,browser-heldout}.json`. Screenshots: `.build/extension-caption.png`, `.build/extension-heldout.png`. Test logs and benchmark scripts remain in the workspace.

## Sources

- [Audio2Emotion model card and restrictions](https://huggingface.co/nvidia/Audio2Emotion-v2.2)
- [emotion2vec+ base card and label ordering](https://huggingface.co/emotion2vec/emotion2vec_plus_base)
- [SenseVoiceSmall](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)
- [FunASR model license](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) — review model-specific terms before redistributing weights or a commercial bundle; no weights are packaged in this extension.
- [Chrome tab capture / offscreen integration](https://developer.chrome.com/docs/extensions/how-to/web-platform/screen-capture)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- [CREMA-D source videos, ratings and license](https://github.com/CheyneyComputerScience/CREMA-D); see DEMO_SOURCES.md. Additional test video IDs are stored in `.build/browser-cases/sources.json`.
