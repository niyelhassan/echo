"""Non-speech sound cues ([laughter], [applause], [music]...) from the AudioSet AST classifier."""
import contextlib
import io
import numpy as np
import torch

REPO = 'mispeech/ced-base'

# Caption label -> AudioSet classes. Thresholds come from evaluate_sounds.py on development videos.
CUES = {
    'laughter': (['Laughter', 'Belly laugh', 'Giggle', 'Chuckle, chortle', 'Snicker', 'Baby laughter'], .30),
    'applause': (['Applause', 'Clapping'], .50),
    'cheering': (['Cheering'], .12),
    'music': (['Music'], .45),
    'singing': (['Singing', 'Choir'], .40),
    'crying': (['Crying, sobbing', 'Baby cry, infant cry', 'Whimper'], .30),
    'shouting': (['Shout', 'Yell', 'Bellow', 'Children shouting'], .30),
    'screaming': (['Screaming'], .30),
    'whispering': (['Whispering'], .35),
    'sighs': (['Sigh'], .55),
    'gasps': (['Gasp'], .60),
    'dog barking': (['Bark', 'Dog'], .40),
    'doorbell': (['Doorbell', 'Ding-dong'], .35),
    'knocking': (['Knock'], .40),
    'phone ringing': (['Telephone bell ringing', 'Ringtone'], .35),
    'alarm': (['Alarm', 'Smoke detector, smoke alarm', 'Fire alarm', 'Buzzer'], .40),
    'siren': (['Siren', 'Police car (siren)', 'Ambulance (siren)', 'Fire engine, fire truck (siren)'], .40),
    'gunshots': (['Gunshot, gunfire', 'Machine gun'], .35),
    'explosion': (['Explosion'], .35),
    'glass breaking': (['Shatter', 'Glass'], .45),
    'thunder': (['Thunder'], .40),
}


class SoundEvents:
    def __init__(self, device=None, model_path=REPO, tile=False):
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        with contextlib.redirect_stderr(io.StringIO()):
            self.extractor = AutoFeatureExtractor.from_pretrained(model_path, trust_remote_code=True)
            self.model = AutoModelForAudioClassification.from_pretrained(model_path, trust_remote_code=True).eval()
        self.device = device or ('mps' if torch.backends.mps.is_available() else 'cpu')
        self.model.to(self.device)
        self.tile = tile
        names = self.model.config.label2id
        self.groups = {cue: ([names[c] for c in classes if c in names], threshold)
                       for cue, (classes, threshold) in CUES.items()}

    def scores(self, audio):
        """Return cue -> score (max sigmoid over its AudioSet classes)."""
        if self.tile:
            audio = np.tile(audio, int(np.ceil(10*16000/len(audio))))[:10*16000]
        features = self.extractor(audio, sampling_rate=16000, return_tensors='pt')['input_values'].to(self.device)
        with torch.inference_mode():
            output = self.model(features).logits
            # CED's head already applies a sigmoid; AST returns raw logits.
            probabilities = (output if self.model.config.model_type == 'ced' else torch.sigmoid(output))[0].cpu().numpy()
        return {cue: float(probabilities[ids].max()) for cue, (ids, _) in self.groups.items()}

    def detect(self, audio, thresholds=None):
        scores = self.scores(audio)
        limits = {cue: t for cue, (_, t) in self.groups.items()} | (thresholds or {})
        cues = sorted((cue for cue, value in scores.items() if value >= limits[cue]), key=scores.get, reverse=True)
        return {'cues': cues, 'scores': {c: round(scores[c], 3) for c in cues}}


if __name__ == '__main__':
    model = SoundEvents()
    print(model.detect(np.random.default_rng(0).normal(0, .05, 48000).astype(np.float32)))
