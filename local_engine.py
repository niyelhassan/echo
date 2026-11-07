"""Streaming utterances plus independent, bounded caption / tone / sound workers (16 kHz PCM)."""
import asyncio
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import time
import numpy as np

RATE = 16000
PACKET = 1600
FIRST_PARTIAL = .5 * RATE
PARTIAL_EVERY = .4 * RATE
END_SILENCE = .4 * RATE
MAX_UTTERANCE = 8 * RATE
SPLIT_SEARCH = 20           # packets (2 s) searched for the quietest split point at the length cap
TONE_AFTER = 2 * RATE       # first tone estimate once an utterance reaches this length
SOUND_WINDOW, SOUND_EVERY = 30, 10   # packets: 3 s window analysed every 1 s
# Silero's default 0.5 misses shouted film dialogue under a music score (see VALIDATION.md).
VAD_THRESHOLD = float(os.environ.get('TONE_CAPTION_VAD', '0.2'))


@dataclass
class Job:
    segment: int
    audio: np.ndarray
    start: float
    end: float
    final: bool
    queued: float


class Segmenter:
    """100 ms packets; VAD ends utterances, a length cap bounds memory and latency."""
    def __init__(self, vad):
        self.vad = vad
        self.position = 0
        self.serial = 0
        self.frames = []
        self.pre = []
        self.silent = 0
        self.last_partial = 0
        self.start = 0

    def push(self, frame):
        jobs = []
        speech = self.vad(frame)
        self.position += len(frame)
        if not self.frames:
            if not speech:
                self.pre = (self.pre + [frame])[-2:]
                return jobs
            self.frames = self.pre
            self.start = self.position - len(frame) - sum(map(len, self.pre))
            self.pre = []
        self.frames.append(frame)
        self.silent = 0 if speech else self.silent + len(frame)
        length = sum(map(len, self.frames))
        if self.silent >= END_SILENCE:
            jobs.append(self.finish())
        elif length >= MAX_UTTERANCE:
            jobs.append(self.split())
        elif length >= FIRST_PARTIAL and length - self.last_partial >= PARTIAL_EVERY:
            self.last_partial = length
            jobs.append(self.job(False))
        return jobs

    def job(self, final, frames=None):
        frames = frames or self.frames
        end = self.start + sum(map(len, frames))
        return Job(self.serial, np.concatenate(frames), self.start/RATE, end/RATE, final, time.perf_counter())

    def split(self):
        """Finalize at the quietest recent packet so a word is less likely to be cut in half."""
        search = self.frames[-SPLIT_SEARCH:]
        quiet = int(np.argmin([float(np.mean(f**2)) for f in search]))
        cut = len(self.frames) - len(search) + quiet + 1
        head, tail = self.frames[:cut], self.frames[cut:]
        job = self.job(True, head)
        self.serial += 1
        self.start += sum(map(len, head))
        self.frames = tail
        self.last_partial = 0
        return job

    def finish(self):
        job = self.job(True) if self.frames else None
        self.frames = []
        self.pre = []
        self.silent = self.last_partial = 0
        self.serial += 1
        return job


class StreamingVAD:
    def __init__(self):
        import torch
        from silero_vad import load_silero_vad
        self.torch = torch
        self.model = load_silero_vad(onnx=True)
        self.pending = np.empty(0, np.float32)

    def __call__(self, frame):
        self.pending = np.concatenate((self.pending, frame))
        probabilities = []
        while len(self.pending) >= 512:
            probabilities.append(float(self.model(self.torch.from_numpy(self.pending[:512].copy()), RATE)))
            self.pending = self.pending[512:]
        return bool(probabilities and max(probabilities) >= VAD_THRESHOLD)


class LocalModels:
    ASR = 'mlx-community/parakeet-tdt-0.6b-v2'
    TONE = 'emotion2vec/emotion2vec_plus_base'

    def __init__(self, download=False):
        import os
        if not download:
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from huggingface_hub import snapshot_download
        import mlx.core as mx
        from parakeet_mlx import from_pretrained
        from parakeet_mlx.audio import get_logmel
        from sound_events import REPO as SOUND_REPO, SoundEvents
        from speech_gate import SpeechGate
        from tone_candidate import CandidateToneModel
        self.mx, self.logmel = mx, get_logmel
        # MLX streams are per-thread: load and run the recognizer on one dedicated thread.
        self.asr_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix='mlx-asr')
        self.asr = self.asr_thread.submit(from_pretrained, self.ASR).result()
        self.tone = CandidateToneModel(model_path=snapshot_download(self.TONE, local_files_only=not download))
        self.sound = SoundEvents(model_path=snapshot_download(SOUND_REPO, local_files_only=not download))
        self.gates = {'text': SpeechGate(), 'tone': SpeechGate()}

    def warm(self):
        silence = np.zeros(RATE, np.float32)
        self.transcribe(silence + np.float32(1e-4))
        self.sound.scores(silence)
        self.tone.predict(np.random.default_rng(0).normal(0, .01, RATE).astype(np.float32))

    def transcribe(self, samples):
        def run():
            return self.asr.generate(self.logmel(self.mx.array(samples), self.asr.preprocessor_config))[0].text.strip()
        return self.asr_thread.submit(run).result()

    def infer(self, channel, samples):
        if channel == 'sound':
            return self.sound.scores(samples)
        if not self.gates[channel].has_speech(samples):
            return {'text': ''} if channel == 'text' else {'tone': None}
        if channel == 'tone':
            return {'tone': self.tone.predict(samples)}
        return {'text': self.transcribe(samples)}


class SoundTracker:
    """Hysteresis: a cue starts at its threshold and persists while above 60% of it.

    A cue that recurs within COOLDOWN updates (seconds) of its last start is not announced again,
    so intermittent sounds such as sobbing read as one cue rather than a stream of repeats.
    """
    COOLDOWN = 12

    def __init__(self, thresholds):
        self.thresholds = thresholds
        self.active = set()
        self.tick = 0
        self.announced = {}

    def update(self, scores):
        self.tick += 1
        active = {c for c, s in scores.items()
                  if s >= self.thresholds[c] or (c in self.active and s >= .6*self.thresholds[c])}
        started = {c for c in active - self.active if self.tick - self.announced.get(c, -self.COOLDOWN) >= self.COOLDOWN}
        ended = self.active - active
        for c in started: self.announced[c] = self.tick
        self.active = active
        return sorted(active, key=scores.get, reverse=True), sorted(started), sorted(ended)


class Session:
    def __init__(self, models, send, vad=None):
        self.models, self.send = models, send
        self.segmenter = Segmenter(vad or StreamingVAD())
        self.queues = {c: asyncio.Queue(maxsize=3) for c in ('text', 'tone', 'sound')}
        self.pools = {c: ThreadPoolExecutor(max_workers=1, thread_name_prefix=c) for c in self.queues}
        self.tasks = [asyncio.create_task(self.worker(c)) for c in self.queues]
        self.failure = None
        self.toned = set()
        self.ring = deque(maxlen=SOUND_WINDOW)
        self.packets = 0
        from sound_events import CUES
        self.sounds = SoundTracker({c: t for c, (_, t) in CUES.items()})

    def replace(self, queue, job, keep):
        pending = []
        while not queue.empty():
            old = queue.get_nowait()
            queue.task_done()
            if keep(old): pending.append(old)
        for old in pending: queue.put_nowait(old)

    def submit(self, job):
        if job is None: return
        # Replace queued revisions of this same utterance; preserve final utterances.
        self.replace(self.queues['text'], job, lambda old: old.segment != job.segment or old.final)
        if self.queues['text'].full():
            raise RuntimeError('Captioning cannot keep up with this audio. Stop and restart; no hidden backlog is kept.')
        self.queues['text'].put_nowait(job)
        long_enough = len(job.audio) >= TONE_AFTER
        if job.final or (long_enough and job.segment not in self.toned):
            if long_enough: self.toned.add(job.segment)
            tone = self.queues['tone']
            self.replace(tone, job, lambda old: old.segment != job.segment)
            if tone.full():
                tone.get_nowait(); tone.task_done()   # tone is best-effort: drop the oldest estimate
            tone.put_nowait(job)

    def submit_sound(self):
        queue = self.queues['sound']
        if queue.full():
            queue.get_nowait(); queue.task_done()
        end = self.packets*PACKET/RATE
        queue.put_nowait(Job(-1, np.concatenate(self.ring), end - len(self.ring)*PACKET/RATE, end, True,
                             time.perf_counter()))

    async def feed(self, audio):
        if self.failure: raise RuntimeError(self.failure)
        self.ring.append(audio)
        self.packets += 1
        if self.packets % SOUND_EVERY == 0 and len(self.ring) >= SOUND_EVERY*2:
            self.submit_sound()
        for job in self.segmenter.push(audio): self.submit(job)

    async def worker(self, channel):
        queue = self.queues[channel]
        while True:
            job = await queue.get()
            try:
                started = time.perf_counter()
                result = await asyncio.get_running_loop().run_in_executor(self.pools[channel], self.models.infer,
                                                                           channel, job.audio)
                timing = {'processing_ms': round((time.perf_counter()-started)*1000),
                          'queue_and_processing_ms': round((time.perf_counter()-job.queued)*1000)}
                if channel == 'sound':
                    active, started_cues, ended = self.sounds.update(result)
                    if started_cues or ended:
                        await self.send({'type': 'sound', 'start': job.start, 'end': job.end, 'active': active,
                                         'started': started_cues, 'ended': ended,
                                         'scores': {c: round(result[c], 3) for c in active}, **timing})
                elif channel == 'tone':
                    if result['tone']:
                        await self.send({'type': 'tone', 'segment': job.segment, 'final': job.final, **result, **timing})
                else:
                    await self.send({'type': 'caption', 'segment': job.segment, 'start': job.start, 'end': job.end,
                                     'final': job.final, **result, **timing})
            except Exception as exc:
                self.failure = str(exc)
                await self.send({'type': 'error', 'message': str(exc)})
            finally:
                queue.task_done()

    async def flush(self):
        self.submit(self.segmenter.finish())
        await asyncio.gather(*(q.join() for q in self.queues.values()))

    async def close(self):
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        # Do not let a new session run against models still executing cancelled work.
        for pool in self.pools.values():
            await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)
