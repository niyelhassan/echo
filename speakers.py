"""Online speaker labels: WeSpeaker ResNet34 (VoxCeleb) embeddings + incremental centroid clustering."""
import numpy as np
import onnxruntime as ort
import torch
import torchaudio

REPO = 'Wespeaker/wespeaker-voxceleb-resnet34-LM'
FILE = 'voxceleb_resnet34_LM.onnx'
MAX_SPEAKERS = 8


class SpeakerEmbedder:
    def __init__(self, model_path, threads=2):
        options = ort.SessionOptions(); options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(model_path, options, providers=['CPUExecutionProvider'])
        self.input = self.session.get_inputs()[0].name

    def embed(self, audio):
        wave = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0) * 32768
        feats = torchaudio.compliance.kaldi.fbank(wave, num_mel_bins=80, frame_length=25, frame_shift=10,
                                                  dither=0.0, sample_frequency=16000, window_type='hamming')
        feats = (feats - feats.mean(0)).numpy()[None].astype(np.float32)
        vector = self.session.run(None, {self.input: feats})[0][0]
        return vector / (np.linalg.norm(vector) + 1e-9)


def learnable(text, seconds):
    """Laughter, crowd noise and one-word replies ("Yeah.") make poor voice prints."""
    return seconds >= 1.5 and len(text.split()) >= 3


class SpeakerTracker:
    """Assigns utterances to the closest known voice; only learnable utterances may add or refine a voice."""

    def __init__(self, threshold=0.35, margin=0.08):
        self.threshold, self.margin = threshold, margin
        self.centroids, self.last = [], None

    def similarities(self, vector):
        return [float(c @ vector / np.linalg.norm(c)) for c in self.centroids]

    def match(self, vector):
        sims = self.similarities(vector)
        if not sims: return None
        best = int(np.argmax(sims))
        if sims[best] >= self.threshold: return best
        if self.last is not None and sims[self.last] >= self.threshold - self.margin: return self.last
        return None

    def assign(self, vector, seconds, learn):
        speaker = self.match(vector)
        if not learn:
            return speaker
        if speaker is None:
            if len(self.centroids) >= MAX_SPEAKERS: return None
            self.centroids.append(np.zeros_like(vector)); speaker = len(self.centroids) - 1
        self.centroids[speaker] = self.centroids[speaker] + vector * min(seconds, 6)
        self.last = speaker
        return speaker
