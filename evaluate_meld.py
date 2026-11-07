"""Vocal-tone accuracy on MELD test (Friends TV dialogue, 2610 utterances, 7 labels).

MELD labels were assigned by annotators who saw video and text, so audio-only scores understate
what a viewer perceives. Even dialogues tune the display policy; odd dialogues are reported.
Usage: uv run --with pyarrow python evaluate_meld.py base|large
"""
import io
import json
import re
import sys
import time
import numpy as np
import soundfile as sf
from real_eval import ROOT

MAP = {'neutral': 'Neutral', 'anger': 'Angry', 'joy': 'Happy', 'sadness': 'Sad', 'surprise': 'Surprised',
       'fear': 'Fearful', 'disgust': 'Disgusted'}


def load():
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download
    table = pq.read_table(hf_hub_download('AudioLLMs/meld_emotion_test', 'data/test-00000-of-00001.parquet',
                                          repo_type='dataset')).to_pylist()
    rows = []
    for i, row in enumerate(table):
        label = next(MAP[w] for w in re.findall(r'[a-z]+', row['answer'].lower()) if w in MAP)
        audio, rate = sf.read(io.BytesIO(row['context']['bytes']), dtype='float32')
        audio = audio.mean(axis=1) if audio.ndim > 1 else audio
        assert rate == 16000, rate
        rows.append({'index': i, 'path': row['context']['path'], 'label': label, 'audio': audio})
    return rows


def main(size):
    from tone_candidate import CandidateToneModel
    from huggingface_hub import snapshot_download
    model = CandidateToneModel(model_path=snapshot_download(f'emotion2vec/emotion2vec_plus_{size}'))
    rows = load()
    out = []
    for row in rows:
        started = time.perf_counter()
        result = model.predict(row['audio']) if len(row['audio']) >= 8000 else {'scores': {}}
        out.append({'index': row['index'], 'path': row['path'], 'label': row['label'],
                    'seconds': len(row['audio'])/16000, 'scores': result['scores'],
                    'ms': (time.perf_counter()-started)*1000})
    (ROOT/f'.build/evaluation/meld-{size}.json').write_text(json.dumps(out))
    print(size, 'done', len(out), 'median ms', np.median([o['ms'] for o in out]))


if __name__ == '__main__':
    main(sys.argv[1])
