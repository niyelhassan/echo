"""Reject non-speech before asking an emotion model to choose an emotion."""
import threading
import numpy as np
import torch
from silero_vad import load_silero_vad, get_speech_timestamps
from local_engine import VAD_THRESHOLD


class SpeechGate:
    def __init__(self):
        self.model = load_silero_vad(onnx=True)
        self.lock = threading.Lock()

    def has_speech(self, audio):
        if len(audio) < 8000 or float(np.sqrt(np.mean(audio**2))) < 0.001:
            return False
        with self.lock:
            timestamps = get_speech_timestamps(torch.from_numpy(audio.copy()), self.model,
                                               sampling_rate=16000, threshold=VAD_THRESHOLD,
                                               min_speech_duration_ms=200, speech_pad_ms=0)
        return sum(t["end"]-t["start"] for t in timestamps) >= 0.25*16000
