"""Threshold-free comparison of sound-cue backends (window AUC, annotated vs. far-from-annotation)."""
import json
import sys
import time
import numpy as np
from real_eval import CASES, ROOT, load_audio, reference
from sound_events import SoundEvents

WINDOW, HOP = 3.0, 1.0
VARIANTS = {
    'ast-padded': dict(model_path='MIT/ast-finetuned-audioset-10-10-0.4593'),
    'ast-tiled': dict(model_path='MIT/ast-finetuned-audioset-10-10-0.4593', tile=True),
    'ced-base': dict(model_path='mispeech/ced-base'),
    'ced-small': dict(model_path='mispeech/ced-small'),
}


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None]).mean() + .5*(pos[:, None] == neg[None]).mean())) if len(pos) and len(neg) else None


def labelled_windows(video, start, end, scores, cue):
    refs = [(a, b) for a, b, s in reference(video, start, end)[1] if s == cue]
    pos = [s[cue] for t, s in scores if any(t < b+1 and t+WINDOW > a-1 for a, b in refs)]
    neg = [s[cue] for t, s in scores if not any(t < b+4 and t+WINDOW > a-4 for a, b in refs)]
    return pos, neg


def main(videos):
    results = {}
    audio = {v: load_audio(v) for v, *_ in CASES}
    for name, kwargs in VARIANTS.items():
        model = SoundEvents(**kwargs)
        model.scores(np.zeros(48000, np.float32))
        timings, per_cue = [], {}
        windows = {}
        for video, start, end, _ in CASES:
            if video not in videos: continue
            rows = []
            for t in np.arange(start, min(end, len(audio[video])/16000) - WINDOW, HOP):
                began = time.perf_counter()
                rows.append((t, model.scores(audio[video][int(t*16000):int((t+WINDOW)*16000)])))
                timings.append((time.perf_counter()-began)*1000)
            windows[video] = rows
        for cue in ('laughter', 'applause'):
            pos, neg = [], []
            for video, start, end, _ in CASES:
                if video in windows:
                    p, n = labelled_windows(video, start, end, windows[video], cue)
                    pos += p; neg += n
            per_cue[cue] = {'auc': auc(pos, neg), 'positives': len(pos), 'negatives': len(neg)}
        results[name] = {'median_ms': round(float(np.median(timings)), 1), **per_cue}
        print(name, results[name], flush=True)
    return results


if __name__ == '__main__':
    split = sys.argv[1]
    videos = {'dev': {'arj7oStGLkU', 'Yvrf-CeBkm4'}, 'test': {'iCvmsMzlF7o', 'mfjnDLbCroQ'}}[split]
    if len(sys.argv) > 2:
        VARIANTS = {k: VARIANTS[k] for k in sys.argv[2:]}
    out = ROOT/f'.build/evaluation/sound-models-{split}.json'
    out.write_text(json.dumps(main(videos), indent=2))
