"""emotion2vec+ candidate: same normalization/head as upstream, without embedding copies."""
import contextlib
import logging
import sys
import numpy as np
import torch

LABELS = ["Angry", "Disgusted", "Fearful", "Happy", "Neutral", "Other", "Sad", "Surprised", "Unknown"]


class CandidateToneModel:
    def __init__(self, device="cpu", threads=4, size="base", model_path=None):
        torch.set_num_threads(threads)
        from funasr import AutoModel
        with contextlib.redirect_stdout(sys.stderr):
            loader = AutoModel(model=model_path or f"emotion2vec/emotion2vec_plus_{size}", hub="hf", device=device,
                               disable_update=True, disable_pbar=True, log_level="ERROR")
        self.model = loader.model.eval()
        self.device = device

    def predict(self, audio):
        if len(audio) < 8000 or float(np.sqrt(np.mean(audio**2))) < 0.001:
            return {"label": "No speech", "scores": {}, "leading": None}
        source = torch.from_numpy(np.asarray(audio, dtype=np.float32).copy()).to(self.device)
        with torch.inference_mode():
            if self.model.cfg.normalize:
                source = torch.nn.functional.layer_norm(source, source.shape)
            features = self.model.extract_features(source.view(1, -1), padding_mask=None)["x"]
            values = self.model.proj(features.mean(dim=1)).softmax(dim=-1)[0].cpu().tolist()
        scores = dict(zip(LABELS, values))
        ranking = sorted(scores, key=scores.get, reverse=True)
        best, second = ranking[:2]
        certain = scores[best] >= 0.55 and scores[best]-scores[second] >= 0.15 and best not in ("Unknown", "Other")
        return {"label": f"Possibly {best.lower()}" if certain else "Uncertain / mixed", "scores": scores,
                "leading": best, "reason": "Vocal expression estimate; sarcasm not evaluated"}
