"""Choose tone display thresholds on even MELD dialogues; report on odd dialogues.

A shown tag is correct when the model's top non-neutral label equals the MELD label.
"""
import json
import re
import sys
from collections import Counter
import numpy as np
from real_eval import ROOT

EMOTIONS = ['Angry', 'Happy', 'Sad', 'Surprised', 'Fearful', 'Disgusted']
TARGETS = {'strict': .75, 'balanced': .60, 'more': .50}


def dialogue(path):
    match = re.search(r'dia(\d+)', path)
    return int(match.group(1)) if match else None


def decide(row, score, margin):
    s = row['scores']
    if not s: return None
    ranked = sorted(s.items(), key=lambda x: -x[1])
    (best, top), second = ranked[0], ranked[1][1]
    return best if best in EMOTIONS and top >= score and top - second >= margin else None


def evaluate(rows, score, margin):
    shown = [(decide(r, score, margin), r['label']) for r in rows]
    shown = [(p, l) for p, l in shown if p]
    correct = sum(p == l for p, l in shown)
    emotional = sum(r['label'] != 'Neutral' for r in rows)
    neutral = sum(r['label'] == 'Neutral' for r in rows)
    return {'score': score, 'margin': margin, 'shown': len(shown), 'precision': correct/len(shown) if shown else None,
            'correct': correct, 'coverage_of_emotional': correct/emotional,
            'neutral_tagged_rate': sum(l == 'Neutral' for _, l in shown)/neutral,
            'per_label_precision': {e: (sum(p == l for p, l in shown if p == e), sum(p == e for p, _ in shown)) for e in EMOTIONS}}


def top_label(row):
    s = {k: v for k, v in row['scores'].items() if k in EMOTIONS + ['Neutral']}
    return max(s, key=s.get) if s else 'Neutral'


def main(size):
    rows = json.loads((ROOT/f'.build/evaluation/meld-{size}.json').read_text())
    ids = [dialogue(r['path']) for r in rows]
    assert None not in ids, rows[0]['path']
    dev = [r for r, d in zip(rows, ids) if d % 2 == 0]
    test = [r for r, d in zip(rows, ids) if d % 2 == 1]
    labels = sorted(set(r['label'] for r in rows))
    recall = {l: np.mean([top_label(r) == l for r in test if r['label'] == l]) for l in labels}
    report = {'model': size, 'dev_utterances': len(dev), 'test_utterances': len(test),
              'test_label_counts': Counter(r['label'] for r in test),
              'test_top1_accuracy': float(np.mean([top_label(r) == r['label'] for r in test])),
              'test_unweighted_recall': float(np.mean(list(recall.values()))), 'test_recall': recall,
              'median_ms': float(np.median([r['ms'] for r in rows])), 'levels': {}}
    grid = [(s, m) for s in np.arange(.3, .99, .05) for m in np.arange(0, .95, .05)]
    for level, target in TARGETS.items():
        candidates = [evaluate(dev, round(s, 2), round(m, 2)) for s, m in grid]
        ok = [c for c in candidates if c['precision'] and c['precision'] >= target and c['shown'] >= 15]
        best = max(ok, key=lambda c: c['correct']) if ok else max(candidates, key=lambda c: c['precision'] or 0)
        report['levels'][level] = {'dev': best, 'test': evaluate(test, best['score'], best['margin'])}
    print(json.dumps(report, indent=1, default=str))
    (ROOT/f'.build/evaluation/meld-{size}-analysis.json').write_text(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main(sys.argv[1])
