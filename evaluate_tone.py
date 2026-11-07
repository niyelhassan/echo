"""Reproducible comparisons against audio-only human votes; no labels enter inference."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import soundfile as sf

parser = argparse.ArgumentParser()
parser.add_argument("--model", choices=["baseline", "candidate"], required=True)
parser.add_argument("--split", choices=["dev", "test"], default="dev")
parser.add_argument("--device", default="cpu")
parser.add_argument("--threads", type=int, default=4)
parser.add_argument("--size", default="base", choices=["base", "large"])
args = parser.parse_args()
root = Path(__file__).resolve().parent / ".build" / "evaluation"
if args.model == "baseline":
    from tone import ToneModel
    model = ToneModel()
else:
    from tone_candidate import CandidateToneModel
    model = CandidateToneModel(device=args.device, threads=args.threads, size=args.size)
items = [x for x in json.loads((root/"manifest.json").read_text()) if x["split"] == args.split]
records = []
for item in items:
    audio, rate = sf.read(item["file"], dtype="float32")
    assert rate == 16000
    started = time.perf_counter()
    prediction = model.predict(audio)
    elapsed = time.perf_counter()-started
    scores = prediction["scores"]
    leading = max(scores, key=scores.get) if scores else None
    records.append({**item, "prediction": prediction, "correct": leading == item["expected"],
                    "seconds": elapsed, "audio_seconds": len(audio)/rate})
    print(item["clip"], item["expected"], leading, round(elapsed, 3), flush=True)
eligible = [r for r in records if r["expected"]]
accepted = [r for r in eligible if r["prediction"]["label"].startswith("Possibly")]
strong = [r for r in eligible if r["agreement"] >= 0.6]
summary = {"model": args.model, "size":args.size, "split": args.split, "device": args.device, "threads": args.threads,
           "count": len(eligible), "ambiguous_votes": len(records)-len(eligible),
           "accuracy": sum(r["correct"] for r in eligible)/len(eligible),
           "strong_agreement_count": len(strong),
           "strong_agreement_accuracy": sum(r["correct"] for r in strong)/len(strong),
           "accepted_count": len(accepted),
           "accepted_accuracy": sum(r["correct"] for r in accepted)/len(accepted) if accepted else None,
           "median_seconds": float(np.median([r["seconds"] for r in records[1:]])),
           "p95_seconds": float(np.percentile([r["seconds"] for r in records[1:]],95)),
           "first_inference_seconds": records[0]["seconds"]}
output = root/f"{args.model}-{args.size}-{args.split}-{args.device}-{args.threads}.json"
output.write_text(json.dumps({"summary":summary,"records":records},indent=2))
print(json.dumps(summary, indent=2))
