"""Measure transcription error and warmed per-utterance inference time."""
import argparse
import json
import re
import time
from pathlib import Path
import mlx_whisper
import numpy as np
import soundfile as sf

def distance(a, b):
    row = list(range(len(b)+1))
    for i,x in enumerate(a,1):
        next_row = [i]
        for j,y in enumerate(b,1):
            next_row.append(min(next_row[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row = next_row
    return row[-1]

parser=argparse.ArgumentParser()
parser.add_argument('--model',default='small')
parser.add_argument('--split',default='dev')
args=parser.parse_args()
repo=f'mlx-community/whisper-{args.model}-mlx'
root=Path('.build/evaluation')
mlx_whisper.transcribe(np.zeros(16000,dtype=np.float32),path_or_hf_repo=repo)
records=[]
for item in json.loads((root/'manifest.json').read_text()):
    if item['split']!=args.split: continue
    audio,rate=sf.read(item['file'],dtype='float32')
    started=time.perf_counter()
    result=mlx_whisper.transcribe(audio,path_or_hf_repo=repo,language='en',temperature=0,condition_on_previous_text=False)
    elapsed=time.perf_counter()-started
    reference="don't forget a jacket" if '_DFA_' in item['clip'] else 'i wonder what this is about'
    normalize=lambda x: re.findall(r"[a-z]+(?:'[a-z]+)?",x.lower())
    a,b=normalize(reference),normalize(result['text'])
    records.append({'clip':item['clip'],'text':result['text'],'reference':reference,
                    'errors':distance(a,b),'words':len(a),'seconds':elapsed})
summary={'model':args.model,'split':args.split,'clips':len(records),
         'wer':sum(x['errors'] for x in records)/sum(x['words'] for x in records),
         'median_seconds':float(np.median([x['seconds'] for x in records])),
         'p95_seconds':float(np.percentile([x['seconds'] for x in records],95))}
(root/f'asr-{args.model}-{args.split}.json').write_text(json.dumps({'summary':summary,'records':records},indent=2))
print(json.dumps(summary))
