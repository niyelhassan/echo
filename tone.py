"""Small local speech-emotion baseline. Scores are uncalibrated model outputs."""
import numpy as np
import torch
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForSequenceClassification

MODEL = "superb/wav2vec2-base-superb-er"
LABELS = {"neu": "Neutral", "hap": "Happy", "sad": "Sad", "ang": "Angry"}


class ToneModel:
    def __init__(self):
        torch.set_num_threads(4)
        self.extractor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL)
        self.model = Wav2Vec2ForSequenceClassification.from_pretrained(MODEL).eval()

    def predict(self, audio):
        # Remove leading/trailing padded silence without using source labels.
        frame = 320
        energy = np.array([np.sqrt(np.mean(audio[i:i+frame] ** 2))
                           for i in range(0, len(audio), frame)])
        active = np.flatnonzero(energy > max(0.003, float(energy.max()) * 0.08))
        if not len(active):
            return {"label": "No speech", "scores": {}, "reason": "No usable audio"}
        audio = audio[max(0, (active[0]-2)*frame):min(len(audio), (active[-1]+3)*frame)]
        if len(audio) < 8000:
            return {"label": "Uncertain", "scores": {}, "reason": "Too little audio"}
        inputs = self.extractor(audio, sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.inference_mode():
            probabilities = self.model(**inputs).logits.softmax(dim=-1)[0].tolist()
        scores = {LABELS[self.model.config.id2label[i]]: round(value, 4)
                  for i, value in enumerate(probabilities)}
        ranking = sorted(scores, key=scores.get, reverse=True)
        best, second = ranking[:2]
        certain = scores[best] >= 0.55 and scores[best]-scores[second] >= 0.15
        return {"label": f"Possibly {best.lower()}" if certain else "Uncertain / mixed",
                "scores": scores, "leading": best,
                "reason": "Vocal expression estimate; sarcasm not evaluated"}
