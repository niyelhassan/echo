"""Compare local ASR engines on real videos using the live service's own VAD segmentation.

Usage: uv run python benchmark_real_asr.py whisper:mlx-community/whisper-base.en-mlx parakeet:mlx-community/parakeet-tdt-0.6b-v2
"""
import json
import os
import sys
import time
import jiwer
import numpy as np
from local_engine import Segmenter, StreamingVAD
from real_eval import CASES, ROOT, load_audio, normalize, reference


def engine(spec):
    kind, repo = spec.split(':', 1)
    if kind == 'whisper':
        import mlx_whisper
        def run(audio):
            result = mlx_whisper.transcribe(audio, path_or_hf_repo=repo, language='en', temperature=0,
                                            condition_on_previous_text=False)
            return ' '.join(s['text'].strip() for s in result.get('segments', []) if s.get('no_speech_prob', 0) < .6)
        return run
    if kind == 'parakeet':
        import mlx.core as mx
        from parakeet_mlx import from_pretrained
        from parakeet_mlx.audio import get_logmel
        model = from_pretrained(repo)
        from speech_gate import SpeechGate
        gate = SpeechGate()
        def run(audio):
            if not gate.has_speech(audio): return ''
            return model.generate(get_logmel(mx.array(audio), model.preprocessor_config))[0].text
        return run
    raise ValueError(spec)


def segments(audio):
    segmenter, finals = Segmenter(StreamingVAD()), []
    for i in range(0, len(audio) - 1599, 1600):
        finals += [j for j in segmenter.push(audio[i:i+1600]) if j and j.final]
    last = segmenter.finish()
    return finals + ([last] if last else [])


def main():
    cached = {}
    report = {}
    for spec in sys.argv[1:]:
        run = engine(spec)
        run(np.zeros(16000, np.float32))
        hyps, refs, times, durations, per_case = [], [], [], [], {}
        for video, start, end, _ in CASES:
            ref, _, (a, b) = reference(video, start, end)
            if video not in cached:
                audio = load_audio(video)[int(max(0, a-.3)*16000):int((b+.3)*16000)]
                cached[video] = segments(audio)
            texts = []
            for job in cached[video]:
                t = time.perf_counter()
                texts.append(run(job.audio))
                times.append((time.perf_counter()-t)*1000)
                durations.append(len(job.audio)/16000)
            hyp = normalize(' '.join(texts))
            per_case[video] = round(jiwer.wer(ref, hyp), 4)
            hyps.append(hyp); refs.append(ref)
        output = jiwer.process_words(refs, hyps)
        spec = f"{spec}@vad{os.environ.get('TONE_CAPTION_VAD','0.5')}"
        report[spec] = {'wer': round(output.wer, 4), 'substitutions': output.substitutions,
                        'deletions': output.deletions, 'insertions': output.insertions,
                        'reference_words': sum(len(r.split()) for r in refs), 'per_video_wer': per_case,
                        'median_ms_per_utterance': round(float(np.median(times)), 1),
                        'p95_ms_per_utterance': round(float(np.percentile(times, 95)), 1),
                        'median_utterance_s': round(float(np.median(durations)), 2),
                        'hypotheses': dict(zip([c[0] for c in CASES], hyps))}
        print(spec, {k: v for k, v in report[spec].items() if k != 'hypotheses'}, flush=True)
    out = ROOT/'.build/evaluation/real-asr.json'
    previous = json.loads(out.read_text()) if out.exists() else {}
    out.write_text(json.dumps(previous | report, indent=2))


if __name__ == '__main__':
    main()
