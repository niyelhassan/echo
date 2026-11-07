"""Evaluate joint ASR/emotion inference against the fixed development and test clips."""
import json,re,time,sys
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from funasr import AutoModel

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]

torch.set_num_threads(4)
model=AutoModel(model='FunAudioLLM/SenseVoiceSmall',hub='hf',device='cpu',disable_update=True,disable_pbar=True,log_level='ERROR')
root=Path('.build/evaluation')
records=[]
for item in json.loads((root/'manifest.json').read_text()):
    audio,rate=sf.read(item['file'],dtype='float32')
    start=time.perf_counter()
    raw=model.generate(input=audio,cache={},language='en',use_itn=True,ban_emo_unk='--force-emotion' in sys.argv)[0]['text']
    elapsed=time.perf_counter()-start
    tags=re.findall(r'<\|([^|]+)\|>',raw)
    text=re.sub(r'<\|[^|]+\|>','',raw).strip()
    label=next((x.title() for x in tags if x in ('HAPPY','SAD','ANGRY','NEUTRAL','FEARFUL','DISGUSTED','SURPRISED')),None)
    ref="don't forget a jacket" if '_DFA_' in item['clip'] else 'i wonder what this is about'
    norm=lambda s:re.findall(r"[a-z]+(?:'[a-z]+)?",s.lower())
    records.append({**item,'raw':raw,'text':text,'leading':label,'correct':label==item['expected'],'seconds':elapsed,'errors':distance(norm(ref),norm(text)),'words':len(norm(ref))})
    print(item['clip'],raw,round(elapsed,3),flush=True)
summary={}
for split in ('dev','test'):
    r=[x for x in records if x['split']==split];eligible=[x for x in r if x['expected']]
    summary[split]={'accuracy':sum(x['correct'] for x in eligible)/len(eligible),'count':len(eligible),'wer':sum(x['errors'] for x in r)/sum(x['words'] for x in r),'median_seconds':float(np.median([x['seconds'] for x in r[1:]]))}
(root/('sensevoice-forced.json' if '--force-emotion' in sys.argv else 'sensevoice.json')).write_text(json.dumps({'summary':summary,'records':records},indent=2))
print(json.dumps(summary))
