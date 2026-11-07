"""Fixed, speaker-separated test set; never select examples by model performance."""
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent / ".build" / "evaluation"
ROOT.mkdir(parents=True, exist_ok=True)
base = "https://raw.githubusercontent.com/CheyneyComputerScience/CREMA-D/master"
for filename in ("summaryTable.csv", "tabulatedVotes.csv"):
    subprocess.run(["curl", "-fLsS", f"{base}/processedResults/{filename}", "-o", str(ROOT/filename)], check=True)
summary = {r["FileName"]: r for r in csv.DictReader((ROOT/"summaryTable.csv").open())}
votes = {r["fileName"]: r for r in csv.DictReader((ROOT/"tabulatedVotes.csv").open()) if r[""].startswith("1")}
labels = {"N": "Neutral", "H": "Happy", "S": "Sad", "A": "Angry", "D": "Disgusted", "F": "Fearful"}
items = []
for actor in range(1001, 1009):
    for sentence in ("DFA", "IWW"):
        for intended in ("NEU", "HAP", "SAD", "ANG"):
            clip = f"{actor}_{sentence}_{intended}_XX"
            vote = summary[clip]["VoiceVote"]
            # Tied human votes remain ambiguous, rather than inventing a truth label.
            expected = labels.get(vote)
            items.append({"clip": clip, "actor": actor, "split": "dev" if actor <= 1004 else "test",
                          "expected": expected, "voice_vote": vote,
                          "agreement": float(votes[clip]["agreement"]),
                          "intended": {"NEU":"Neutral", "HAP":"Happy", "SAD":"Sad", "ANG":"Angry"}[intended],
                          "file": str(ROOT/f"{clip}.wav")})

def download(item):
    if Path(item["file"]).exists():
        return
    url = f"https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/AudioWAV/{item['clip']}.wav"
    subprocess.run(["curl", "-fLsS", "--max-time", "60", url, "-o", item["file"]], check=True)

with ThreadPoolExecutor(max_workers=4) as executor:
    list(executor.map(download, items))
(ROOT/"manifest.json").write_text(json.dumps(items, indent=2))
print(f"Prepared {len(items)} clips; 32 development and 32 held-out clips on disjoint speakers.")
