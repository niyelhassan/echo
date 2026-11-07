"""Capture an explicitly selected input/loopback device; emit local JSON lines.

This first milestone transcribes audio. Emotion and sarcasm are not implemented.
"""
import argparse
import json
import math
import queue
import sys
import time
import subprocess
import threading
from pathlib import Path
from contextlib import contextmanager

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly


@contextmanager
def system_stream(callback):
    root = Path(__file__).resolve().parent
    binary = root / ".build" / "system-audio"
    source = root / "SystemAudio.swift"
    binary.parent.mkdir(exist_ok=True)
    if not binary.exists() or source.stat().st_mtime > binary.stat().st_mtime:
        subprocess.run(["xcrun", "swiftc", "-parse-as-library", str(source), "-o", str(binary)], check=True)
    process = subprocess.Popen([str(binary)], stdout=subprocess.PIPE)

    def read_audio():
        position = 0
        while True:
            raw = process.stdout.read(6400)
            if not raw:
                break
            block = np.frombuffer(raw, dtype="<f4").copy()
            callback(position, block)
            position += len(block)
        callback(position, None)

    reader = threading.Thread(target=read_audio, daemon=True)
    reader.start()
    try:
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=3)
        process.stdout.close()


def audio_metrics(audio, rate):
    """Digital level measurements, not perceived emotion or calibrated SPL."""
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return {
        "rms_dbfs": round(20 * math.log10(max(rms, 1e-10)), 1),
        "clipped_fraction": round(float(np.mean(np.abs(audio) >= 0.999)), 4),
        "duration_seconds": round(len(audio) / rate, 3),
    }


def as_16khz(audio, rate):
    divisor = math.gcd(rate, 16000)
    return resample_poly(audio, 16000 // divisor, rate // divisor).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=int, help="Input device ID; use a loopback for system sound")
    parser.add_argument("--system", action="store_true", help="Capture macOS system audio natively")
    parser.add_argument("--pretty", action="store_true", help="Show readable captions instead of JSON")
    parser.add_argument("--seconds", type=float, default=5, help="Chunk duration, 1–30 seconds")
    parser.add_argument("--model", default="mlx-community/whisper-small-mlx")
    parser.add_argument("--language", default="en", help="Language code, or auto")
    parser.add_argument("--silence-db", type=float, default=-55)
    args = parser.parse_args()
    if args.list_devices:
        print(sd.query_devices())
        return
    if args.device is None and not args.system:
        parser.error("Select --system or --device explicitly; run --list-devices first.")
    if args.system and args.device is not None:
        parser.error("Choose --system or --device, not both")
    if not 1 <= args.seconds <= 30:
        parser.error("--seconds must be between 1 and 30")

    import mlx_whisper

    if args.system:
        rate, channels = 16000, 1
        device = {"name": "macOS system audio"}
    else:
        device = sd.query_devices(args.device, "input")
        rate = int(device["default_samplerate"])
        channels = min(2, int(device["max_input_channels"]))
        sd.check_input_settings(device=args.device, channels=channels, samplerate=rate, dtype="float32")
    # Warm up before capturing so model download/loading cannot create a backlog.
    print("Loading local model (first run may download weights)…", file=sys.stderr)
    mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32), path_or_hf_repo=args.model)
    blocks = queue.Queue(maxsize=100)  # bounded: approximately ten seconds
    sample_position = 0
    dropped_frames = 0
    input_overflows = 0

    def enqueue(start, block):
        nonlocal dropped_frames
        if block is None:
            blocks.put((start, None))
            return
        try:
            blocks.put_nowait((start, block))
        except queue.Full:
            dropped_frames += len(block)

    def callback(indata, frames, timing, status):
        nonlocal sample_position, dropped_frames, input_overflows
        if status.input_overflow:
            input_overflows += 1
        start = sample_position
        sample_position += frames
        enqueue(start, indata.mean(axis=1).copy())

    target = int(rate * args.seconds)
    pending = np.empty(0, dtype=np.float32)
    pending_start = 0
    expected = 0
    print(f"Capturing {device['name']}; Ctrl-C stops. {'Captions' if args.pretty else 'JSON transcript'} go to stdout.", file=sys.stderr)
    try:
        stream = system_stream(enqueue) if args.system else sd.InputStream(
            device=args.device, samplerate=rate, channels=channels,
            dtype="float32", blocksize=max(1, rate // 10), callback=callback)
        with stream:
            while True:
                try:
                    start, block = blocks.get(timeout=10)
                except queue.Empty:
                    if args.system:
                        print("Waiting for system audio; check recording permission and play a video.", file=sys.stderr)
                        continue
                    raise
                if block is None:
                    raise SystemExit("System capture exited; see the permission/error message above.")
                if start != expected:
                    # Never join audio across missing samples as if it were continuous.
                    pending = np.empty(0, dtype=np.float32)
                    print("Audio queue gap: discarded partial chunk. Try a smaller model.", file=sys.stderr)
                expected = start + len(block)
                if not len(pending):
                    pending_start = start
                pending = np.concatenate((pending, block))
                if len(pending) < target:
                    continue
                chunk, pending = pending[:target], pending[target:]
                chunk_start = pending_start
                pending_start += target
                metrics = audio_metrics(chunk, rate)
                if metrics["rms_dbfs"] < args.silence_db:
                    continue
                started = time.monotonic()
                result = mlx_whisper.transcribe(
                    as_16khz(chunk, rate), path_or_hf_repo=args.model,
                    language=None if args.language == "auto" else args.language,
                    condition_on_previous_text=False, temperature=0,
                )
                segments = [
                    {"start": round(chunk_start / rate + seg["start"], 3),
                     "end": round(chunk_start / rate + seg["end"], 3), "text": seg["text"].strip()}
                    for seg in result.get("segments", [])
                    if seg.get("no_speech_prob", 0) < 0.6
                ]
                if segments:
                    if args.pretty:
                        for segment in segments:
                            timestamp = segment["start"]
                            print(f"[{int(timestamp // 60):02}:{timestamp % 60:04.1f}] {segment['text']}", flush=True)
                        continue
                    print(json.dumps({
                        "segments": segments, "audio": metrics,
                        "emotion": None, "sarcasm": None,
                        "interpretation_status": "not_implemented",
                        "inference_seconds": round(time.monotonic() - started, 2),
                        "dropped_audio_seconds": round(dropped_frames / rate, 2),
                        "input_overflows": input_overflows,
                    }, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        print("Stopped; final incomplete chunk was discarded.", file=sys.stderr)
    except queue.Empty:
        raise SystemExit("No audio callbacks for five seconds. Check the selected device.")


if __name__ == "__main__":
    main()
