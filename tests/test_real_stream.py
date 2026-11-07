"""Real videos, paced in real time through the authenticated WebSocket service.

Measures what a viewer gets: live-caption WER (final captions), delay from speech onset to first text,
delay from end of speech to the final caption, and sound cues near human annotations.
Usage: uv run python tests/test_real_stream.py [seconds-per-video]
"""
import asyncio, json, sys, time
from pathlib import Path
import jiwer
import numpy as np
from websockets.asyncio.client import connect
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from real_eval import CASES, load_audio, normalize, reference

TOKEN = (ROOT/'.build/local-token').read_text().strip()


async def replay(audio):
    events = []
    async with connect('ws://127.0.0.1:8765', max_size=2**20) as ws:
        await ws.send(json.dumps({'token': TOKEN}))
        assert json.loads(await ws.recv())['type'] == 'ready'
        started = time.perf_counter()

        async def receive():
            async for raw in ws:
                e = json.loads(raw); e['wall'] = time.perf_counter() - started; events.append(e)
                if e['type'] == 'error': raise AssertionError(e)
                if e['type'] == 'flushed': return
        receiver = asyncio.create_task(receive())
        # Same clamp as extension/pcm-worklet.js; decoded AAC can overshoot full scale.
        padded = np.clip(np.pad(audio, (0, (-len(audio)) % 1600)), -1, 1)
        for i in range(0, len(padded), 1600):
            await ws.send(padded[i:i+1600].astype('<f4').tobytes())
            await asyncio.sleep(max(0, started + (i+1600)/16000 - time.perf_counter()))
        await ws.send(json.dumps({'type': 'flush'}))
        await asyncio.wait_for(receiver, 30)
    return events


async def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 90
    report, refs, hyps = {}, [], []
    for video, start, end, description in CASES:
        end = min(end, start + seconds)
        ref, sounds, (a, b) = reference(video, start, end)
        offset = max(0, a - .3)
        audio = load_audio(video)[int(offset*16000):int((b+.3)*16000)]
        events = await replay(np.concatenate((audio, np.zeros(8000, np.float32))))
        captions = [e for e in events if e['type'] == 'caption']
        finals = {e['segment']: e for e in captions if e['final']}
        first_text = {}
        for e in captions:
            if e.get('text') and e['segment'] not in first_text: first_text[e['segment']] = e
        onset = [first_text[s]['wall'] - finals[s]['start'] for s in finals if s in first_text]
        finish = [finals[s]['wall'] - finals[s]['end'] for s in finals if finals[s].get('text')]
        hyp = normalize(' '.join(finals[s].get('text', '') for s in sorted(finals)))
        sound_events = [e for e in events if e['type'] == 'sound']
        tones = [e for e in events if e['type'] == 'tone' and e['final']]
        annotated = [(x - offset, y - offset, cue) for x, y, cue in sounds]
        detected_laughs = [e['end'] for e in sound_events if 'laughter' in e['started']]
        hit = sum(any(x-2 <= t <= y+4 for t in detected_laughs) for x, y, cue in annotated if cue == 'laughter')
        report[video] = {
            'description': description, 'seconds': len(audio)/16000, 'wer': round(jiwer.wer(ref, hyp), 4),
            'reference_words': len(ref.split()), 'utterances': len(finals),
            'onset_to_first_text_s': {'median': round(float(np.median(onset)), 2), 'p90': round(float(np.percentile(onset, 90)), 2)},
            'speech_end_to_final_s': {'median': round(float(np.median(finish)), 2), 'p90': round(float(np.percentile(finish, 90)), 2)},
            'p95_queue_and_processing_ms': float(np.percentile([e['queue_and_processing_ms'] for e in captions], 95)),
            'sound_cues': [(round(e['end'], 1), e['started']) for e in sound_events if e['started']],
            'annotated_laughter': sum(c == 'laughter' for *_, c in annotated), 'annotated_laughter_cued': hit,
            'tone_labels': [(e['segment'], max(e['tone']['scores'], key=e['tone']['scores'].get) if e['tone'].get('scores') else None,
                             round(max(e['tone']['scores'].values()), 3) if e['tone'].get('scores') else None) for e in tones],
            'captions': [finals[s].get('text', '') for s in sorted(finals)],
        }
        if video != '_p_-5jYXgbc': refs.append(ref); hyps.append(hyp)
        print(video, {k: v for k, v in report[video].items() if k not in ('captions', 'tone_labels', 'sound_cues')}, flush=True)
    report['overall_wer_excluding_broadcast_reference'] = round(jiwer.wer(refs, hyps), 4)
    print('overall WER', report['overall_wer_excluding_broadcast_reference'])
    (ROOT/'.build/evaluation/real-stream.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
