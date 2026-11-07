"""Download a small, attributed CREMA-D video selection; no labels go to inference."""
import json
from pathlib import Path
import subprocess
import math

ROOT = Path(__file__).resolve().parent
OUT = ROOT / ".build" / "emotion-demo"
OUT.mkdir(parents=True, exist_ok=True)
clips = [f"{actor}_DFA_{emotion}_XX" for actor in (1001, 1002)
         for emotion in ("NEU", "HAP", "SAD", "ANG")]
entries = []
inputs = []
filters = []
offset = 0
for index, clip in enumerate(clips):
    url = f"https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/VideoFlash/{clip}.flv"
    original = OUT / f"{clip}.flv"
    if not original.exists():
        subprocess.run(["curl", "--fail", "-L", "--max-time", "60", "-sS", url, "-o", str(original)], check=True)
    metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                                                   "format=duration", "-of", "json", str(original)]))
    duration = math.ceil(float(metadata["format"]["duration"])*30)/30
    inputs += ["-i", str(original)]
    # Normalize all clips before a single encode, avoiding per-file AAC delay and
    # mismatched timestamps. At most a few source frames fill the container tail.
    filters += [f"[{index}:v]setpts=PTS-STARTPTS,scale=640:480,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=0.1,trim=duration={duration}[v{index}]",
                f"[{index}:a]aresample=48000,asetpts=PTS-STARTPTS,apad,atrim=duration={duration}[a{index}]"]
    entries.append({"source": url, "file": clip, "start": offset, "end": offset+duration})
    offset += duration
filters.append("".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]")
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *inputs,
                "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-movflags", "+faststart",
                str(OUT / "expressive-speech.mp4")], check=True)
(OUT / "sources.json").write_text(json.dumps(entries, indent=2))
(OUT / "segments.json").write_text(json.dumps([{"start": e["start"], "end": e["end"]} for e in entries]))
print(OUT / "expressive-speech.mp4")
