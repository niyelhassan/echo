"""Local paced-video demo: independent caption/tone workers, bounded work, revisable results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import mlx_whisper
import numpy as np
from speech_gate import SpeechGate
from tone_candidate import CandidateToneModel


def emit(**event):
    print(json.dumps(event), flush=True)


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('--segments', help='Timestamp-only boundaries for an edited demo')
    parser.add_argument('--fast', action='store_true', help='Offline final-result validation')
    parser.add_argument('--clock-stdin', action='store_true', help='Use actual video playback time from JSON stdin')
    parser.add_argument('--asr-model', default='base.en')
    args = parser.parse_args()
    repo = f'mlx-community/whisper-{args.asr_model}-mlx'
    emit(status='Loading local speech and tone models…')
    tone_model = CandidateToneModel()
    gate = SpeechGate()
    # Decode once, but expose only audio that has actually played to inference.
    raw = subprocess.check_output(['ffmpeg', '-nostdin', '-v', 'error', '-i', args.video,
                                   '-t', '60', '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1'])
    audio = np.frombuffer(raw, dtype='<f4').copy()
    duration = len(audio)/16000
    if not duration:
        raise ValueError('The video contains no decoded audio')
    boundaries = json.loads(Path(args.segments).read_text()) if args.segments else [
        {'start': s, 'end': min(s+5, duration)} for s in np.arange(0, duration, 5).tolist()]
    previous = 0
    for b in boundaries:
        if abs(b['start']-previous) > .001 or b['end'] <= previous or b['end'] > duration+.04:
            raise ValueError('Segment times must be continuous, increasing and within the video')
        b['end'] = min(b['end'], duration)
        previous = b['end']
    duration = boundaries[-1]['end']
    commands = deque()
    command_lock = threading.Lock()

    def read_clock():
        for line in sys.stdin:
            try:
                value = json.loads(line)
            except ValueError:
                continue
            with command_lock:
                # Preserve reset commands; coalesce playback updates.
                if 'playback' in value and commands and 'playback' in commands[-1]:
                    commands[-1] = value
                else:
                    commands.append(value)
        with command_lock:
            commands.append({'quit': True})

    def infer(channel, samples):
        began = time.perf_counter()
        speech = gate.has_speech(samples)
        if channel == 'tone':
            result = {'tone': tone_model.predict(samples) if speech else
                      {'label': 'No clear speech', 'scores': {}, 'leading': None}}
        elif speech:
            result = mlx_whisper.transcribe(samples, path_or_hf_repo=repo, language='en',
                                            temperature=0, condition_on_previous_text=False)
            result = {'text': ' '.join(s['text'].strip() for s in result.get('segments', [])
                                      if s.get('no_speech_prob', 0) < .6)}
        else:
            result = {'text': ''}
        result['inference_seconds'] = round(time.perf_counter()-began, 4)
        return result

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='captions') as caption_pool, \
         ThreadPoolExecutor(max_workers=1, thread_name_prefix='tone') as tone_pool:
        pools = {'text': caption_pool, 'tone': tone_pool}
        # Warm ASR on the same thread used during playback.
        caption_pool.submit(mlx_whisper.transcribe, np.zeros(16000, dtype=np.float32),
                            path_or_hf_repo=repo).result()
        tone_pool.submit(tone_model.predict, np.sin(np.arange(16000,dtype=np.float32)*.1)*.01).result()
        if args.clock_stdin:
            threading.Thread(target=read_clock, daemon=True).start()
        while True:
            playhead = 0.0
            submitted = {k: set() for k in pools}
            finished = {k: set() for k in pools}
            running = {}
            partial_at = {}
            available_at = {}
            completed = False
            started = time.perf_counter()
            emit(ready=True, duration=duration)
            while True:
                reset = False
                if args.clock_stdin:
                    with command_lock:
                        incoming = list(commands)
                        commands.clear()
                    for command in incoming:
                        if command.get('quit'):
                            return
                        if command.get('reset') and completed:
                            reset = True
                        if 'playback' in command:
                            playhead = max(playhead, min(float(command['playback']), duration))
                else:
                    playhead = duration if args.fast else min(time.perf_counter()-started, duration)
                if reset:
                    break
                now = time.perf_counter()
                # Available timestamps include scheduling/queue delays in reported latency.
                for i,b in enumerate(boundaries):
                    if playhead >= b['end']-.01:
                        available_at.setdefault(i, now)
                for channel, (future, meta) in list(running.items()):
                    if not future.done():
                        continue
                    result = future.result()
                    if meta['final']:
                        finished[channel].add(meta['segment'])
                    emit(**result, **{k:v for k,v in meta.items() if k!='available'},
                         provisional=not meta['final'],
                         latency_seconds=round(now-meta['available'],4),
                         playback_seconds=round(playhead,3))
                    del running[channel]
                if not completed and all(len(finished[k]) == len(boundaries) for k in pools):
                    completed = True
                    emit(done=True, status='Finished. Replay is ready immediately; models remain loaded.')
                    if not args.clock_stdin:
                        return
                if completed:
                    time.sleep(.01)
                    continue
                for channel, pool in pools.items():
                    if channel in running:
                        continue  # bounded: at most one in-flight task per channel
                    pending = [i for i in available_at if i not in submitted[channel]]
                    if pending:
                        i = min(pending)
                        b = boundaries[i]
                        end = b['end']
                        final = True
                        submitted[channel].add(i)
                        available = available_at[i]
                    else:
                        active = [i for i,b in enumerate(boundaries) if b['start'] <= playhead < b['end']]
                        if not active:
                            continue
                        i = active[0]
                        b = boundaries[i]
                        end = playhead
                        minimum = .8 if channel == 'tone' else 1.2
                        interval = .4 if channel == 'tone' else .8
                        if end-b['start'] < minimum or end-partial_at.get((channel,i),b['start']) < interval:
                            continue
                        if b['end']-end < .15:
                            continue
                        partial_at[channel,i] = end
                        final = False
                        available = now
                    samples = audio[round(b['start']*16000):round(end*16000)].copy()
                    meta = {'start': round(b['start'],3), 'end': round(end,3), 'final':final,
                            'segment':i, 'available':available}
                    running[channel] = (pool.submit(infer, channel, samples), meta)
                time.sleep(.01)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit(status=f'Demo stopped: {error}', done=True)
        raise
