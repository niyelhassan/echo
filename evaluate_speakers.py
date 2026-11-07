"""Calibrate speaker labels on real clips: speakers opened per threshold, plus a labelled transcript to review."""
import argparse
import numpy as np
from huggingface_hub import hf_hub_download
from local_engine import PACKET, Segmenter, StreamingVAD
from real_eval import load_audio
from speakers import FILE, REPO, SpeakerEmbedder, SpeakerTracker, learnable

CLIPS = [c for c in [('arj7oStGLkU', 60, 240, 1), ('iCvmsMzlF7o', 60, 240, 1), ('nsEq3XDq9gQ', 0, 75, 2),
         ('Yvrf-CeBkm4', 0, 175, None), ('_p_-5jYXgbc', 0, 96, None), ('S7OWoc-j8qQ', 0, 146, None)] if __import__('os').environ.get('ONLY', c[0]) == c[0]]


def utterances(audio):
    segmenter, out = Segmenter(StreamingVAD()), []
    for i in range(0, len(audio) - PACKET, PACKET):
        out += [j for j in segmenter.push(audio[i:i+PACKET]) if j and j.final]
    last = segmenter.finish()
    return out + ([last] if last else [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', action='store_true', help='transcribe utterances for manual review')
    parser.add_argument('--threshold', type=float, default=0.35)
    args = parser.parse_args()
    from local_engine import LocalModels
    embedder, models = SpeakerEmbedder(hf_hub_download(REPO, FILE)), LocalModels()
    for video, start, end, expected in CLIPS:
        audio = np.clip(load_audio(video)[start*16000:end*16000], -1, 1)
        jobs = utterances(audio)
        rows = [(embedder.embed(j.audio), len(j.audio)/16000, models.transcribe(j.audio), j.start+start) for j in jobs]
        counts = {}
        for threshold in (0.3, 0.35, 0.4, 0.45, 0.5):
            tracker = SpeakerTracker(threshold)
            labels = [tracker.assign(v, sec, learnable(t, sec)) for v, sec, t, _ in rows]
            shown = [l for l in labels if l is not None]
            counts[threshold] = f'{len(tracker.centroids)}spk/{sum(a != b for a, b in zip(shown, shown[1:]))}chg'
        print(video, f'{len(jobs)} utterances, expected {expected or "?"} speakers', counts, flush=True)
        if args.text:
            tracker = SpeakerTracker(args.threshold)
            for v, sec, text, at in rows:
                speaker = tracker.assign(v, sec, learnable(text, sec))
                print(f'  {at:6.1f}s S{"-" if speaker is None else speaker+1}: {text}')


if __name__ == '__main__':
    main()
