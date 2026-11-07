"""Real-video evaluation helpers: human VTT references, text normalization, and test windows."""
import html
import re
import subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
REAL = ROOT/'.build/real'

# (video id, start s, end s, description). Windows are fixed before any model is run.
CASES = [
    ('arj7oStGLkU', 60, 300, 'TED talk, audience laughter and applause'),
    ('iCvmsMzlF7o', 60, 300, 'TED talk, conversational delivery, laughter'),
    ('mfjnDLbCroQ', 60, 300, 'Stand-up comedy, shouting, crowd laughter, music'),
    ('nsEq3XDq9gQ', 0, 75, 'Film scene, two speakers, heated argument'),
    ('Yvrf-CeBkm4', 0, 175, 'Comedy sketch with laugh track, several speakers'),
    ('_p_-5jYXgbc', 0, 96, 'TV news story, field interviews, emotional reunion'),
    ('S7OWoc-j8qQ', 0, 146, 'Film clip (Home Alone), shouting over a loud score'),
]

SOUND_PATTERNS = {
    'laughter': r'laugh',
    'applause': r'applause|clap',
    'cheering': r'cheer',
    'music': r'music|♪',
}
FILLERS = {'um', 'uh', 'erm', 'hmm', 'mm', 'ah', 'oh', 'er'}


def vtt_path(video):
    return next(REAL.glob(f'{video}.en*.vtt'))


def parse_time(value):
    h, m, s = value.split(':') if value.count(':') == 2 else ('0', *value.split(':'))
    return int(h)*3600 + int(m)*60 + float(s)


def cues(video):
    blocks = vtt_path(video).read_text().split('\n\n')
    result = []
    for block in blocks:
        lines = block.strip().splitlines()
        stamp = next((i for i, l in enumerate(lines) if '-->' in l), None)
        if stamp is None:
            continue
        start, end = (parse_time(x.split()[0]) for x in lines[stamp].split('-->'))
        text = html.unescape(re.sub(r'<[^>]+>', '', ' '.join(lines[stamp+1:]))).replace('\xa0', ' ')
        result.append((start, end, ' '.join(text.split())))
    return result


def sound_annotations(text):
    marks = ' '.join(''.join(g) for g in re.findall(r'\(([^)]*)\)|\[([^\]]*)\]|\*([^*]*)\*', text))
    if re.fullmatch(r'\s*audience laughs\s*', text, re.I):
        marks += ' laugh'
    if '♪' in text:
        marks += ' music'
    return {k for k, p in SOUND_PATTERNS.items() if re.search(p, marks, re.I)}


def spoken(text):
    text = re.sub(r'\([^)]*\)|\[[^\]]*\]|\*[^*]*\*', ' ', text)
    text = re.sub(r'^\s*audience laughs\s*$', ' ', text, flags=re.I)
    text = re.sub(r'^\s*[A-Z][A-Za-z .]*:\s', ' ', text)  # speaker labels
    return text.replace('>>', ' ').replace('Reporter:', ' ')


def normalize(text):
    text = text.lower().replace('’', "'").replace('-', ' ').replace('%', ' percent')
    text = re.sub(r"[^a-z0-9' ]", ' ', text)
    words = [w.strip("'") for w in text.split()]
    return ' '.join(w for w in words if w and w not in FILLERS)


def reference(video, start, end):
    """Spoken reference words and sound annotations for cues fully inside the window."""
    inside = [c for c in cues(video) if c[0] >= start and c[1] <= end]
    words = normalize(' '.join(spoken(c[2]) for c in inside))
    sounds = [(c[0], c[1], s) for c in inside for s in sound_annotations(c[2])]
    return words, sounds, (inside[0][0], inside[-1][1]) if inside else (start, end)


def load_audio(video, rate=16000):
    path = REAL/f'{video}.mp4'
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-ac', '1', '-ar', str(rate),
                          '-f', 'f32le', '-'], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()
