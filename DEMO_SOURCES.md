# Expressive speech demo

Source: [CREMA-D — Crowd-sourced Emotional Multimodal Actors Dataset](https://github.com/CheyneyComputerScience/CREMA-D), Cao et al., 2014.

The local demo contains eight short online video recordings: actors 1001 and 1002 saying the same sentence with neutral, happy, sad and angry delivery. The original recordings are concatenated at their natural durations into an approximately 18-second montage, with a single constant-30-fps encode. There are cuts between recordings, but no multi-second freeze padding. No emotion names are burned into the video, and dataset labels/filenames are not supplied to the inference model. The downloaded source manifest is `.build/emotion-demo/sources.json`. Timestamp-only `segments.json` aligns analysis with each recording rather than mixing different deliveries into fixed five-second chunks.

CREMA-D is available under the [Open Database License](https://opendatacommons.org/licenses/odbl/1-0/); individual contents under the [Database Contents License](https://opendatacommons.org/licenses/dbcl/1-0/).

Audio emotion model: [SUPERB Wav2Vec2 emotion recognition](https://huggingface.co/superb/wav2vec2-base-superb-er), Apache 2.0, trained for four categories on IEMOCAP. This small baseline was selected for straightforward local inference. Predictions on CREMA-D are cross-dataset and can be wrong. Model scores are not probabilities of a person's actual feelings. Sarcasm is outside this model's vocabulary.

Initial validation found happy/angry confusion in these clips, including confident errors. The demo demonstrates the running pipeline, not validated emotion accuracy. Labels say “possibly” and abstain when the top score is below 0.55 or its margin over the runner-up is below 0.15; these are provisional heuristics, not calibrated thresholds.

Prepare: `uv run python prepare_demo.py`. Run: `.build/video-demo "$PWD" "$PWD/.build/emotion-demo/expressive-speech.mp4"` after compiling `VideoDemo.swift`.
