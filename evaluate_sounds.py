"""Score sound cues against human caption annotations on real videos.

Development videos tune thresholds; test videos are only scored. Human captioners do not mark
every sound, so precision here is a lower bound (an unmarked real chuckle counts as false).
"""
import json
import sys
import numpy as np
from real_eval import CASES, ROOT, load_audio, reference
from sound_events import SoundEvents

DEV = {'arj7oStGLkU', 'Yvrf-CeBkm4'}
WINDOW, HOP = 3.0, 1.0
SCORED = ('laughter', 'applause', 'cheering', 'music')
TOLERANCE = 2.0


def window_scores(model):
    cache = ROOT/'.build/evaluation/sound-windows-ced-base.json'
    if cache.exists():
        return json.loads(cache.read_text())
    out = {}
    for video, start, end, _ in CASES:
        audio = load_audio(video)
        rows = []
        for t in np.arange(start, min(end, len(audio)/16000) - WINDOW, HOP):
            rows.append([float(t), model.scores(audio[int(t*16000):int((t+WINDOW)*16000)])])
        out[video] = rows
        print(video, len(rows), flush=True)
    cache.write_text(json.dumps(out))
    return out


def episodes(rows, cue, threshold):
    hits = [t for t, s in rows if s[cue] >= threshold]
    merged = []
    for t in hits:
        if merged and t <= merged[-1][1]:
            merged[-1][1] = t + WINDOW
        else:
            merged.append([t, t + WINDOW])
    return merged


def score(videos, scores, cue, threshold):
    tp_ref = n_ref = tp_det = n_det = 0
    for video, start, end, _ in CASES:
        if video not in videos:
            continue
        refs = [(a, b) for a, b, s in reference(video, start, end)[1] if s == cue or
                (cue == 'cheering' and s == 'applause') or (cue == 'applause' and s == 'cheering')]
        detected = episodes(scores[video], cue, threshold)
        near = lambda d, r: d[0] <= r[1] + TOLERANCE and d[1] >= r[0] - TOLERANCE
        n_ref += len(refs); tp_ref += sum(any(near(d, r) for d in detected) for r in refs)
        n_det += len(detected); tp_det += sum(any(near(d, r) for r in refs) for d in detected)
    return {'threshold': threshold, 'recall': tp_ref/n_ref if n_ref else None, 'references': n_ref,
            'precision_lower_bound': tp_det/n_det if n_det else None, 'detections': n_det}


def main():
    scores = window_scores(SoundEvents())
    from sound_events import CUES
    report = {}
    test = {c[0] for c in CASES} - DEV
    for cue in SCORED:
        dev = [score(DEV, scores, cue, t) for t in (.05, .08, .1, .12, .15, .2, .25, .3, .4, .5)]
        report[cue] = {'dev_sweep': dev, 'configured': CUES[cue][1],
                       'test': score(test, scores, cue, CUES[cue][1])}
        print(cue, 'dev', [(d['threshold'], d['recall'], d['precision_lower_bound']) for d in dev])
        print(cue, 'test', report[cue]['test'])
    # False alarms on clips whose captions mark no non-speech sounds at all.
    for video in ('nsEq3XDq9gQ', '_p_-5jYXgbc'):
        report[f'unmarked-{video}'] = {cue: len(episodes(scores[video], cue, CUES[cue][1])) for cue in CUES
                                       if episodes(scores[video], cue, CUES[cue][1])}
        print('detections on unmarked clip', video, report[f'unmarked-{video}'])
    (ROOT/'.build/evaluation/real-sounds.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
