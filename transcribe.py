#!/usr/bin/env python3
"""Turn every audio and video file in a folder into a text file with timestamps. Runs offline on the CPU,
resumes where it stopped, and keeps memory low enough for a small laptop.

  transcribe.py SOURCE OUT [--model base.en] [--language en] [--threads 2]
  transcribe.py SOURCE OUT --only "lecture 03"        just the files whose path contains that text

  SOURCE  a folder (searched with all its subfolders) or one file
  OUT     where the .txt files go, mirroring SOURCE's folders. A file that's already there is skipped.

Each file is cut into 20-minute pieces first, so a 3-hour video never has to fit in memory at once. Every piece
is saved as it finishes: stop it any time (Ctrl-C, a reboot, memguard.sh) and the next run picks up at that piece.
Timestamps stay true to the whole file: [1:02:15] means an hour, two minutes and fifteen seconds in.

Models (bigger = slower and more accurate): tiny.en, base.en, small.en, medium.en, large-v3 (any language).
Needs ffmpeg and:  pip install faster-whisper
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

MEDIA = {".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".opus", ".aac", ".wma",
         ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}
CHUNK = 1200  # seconds per piece


def stamp(s):
    s = int(s)
    return f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}]"


def files(source, only=None):
    src = Path(source)
    found = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.suffix.lower() in MEDIA and p.is_file())
    return [p for p in found if not only or only.lower() in str(p).lower()]


def out_path(f, source, out):
    src = Path(source)
    rel = f.name if src.is_file() else f.relative_to(src)
    return Path(out) / Path(rel).with_suffix(".txt")


def split(f, work):
    """16 kHz mono WAV pieces of CHUNK seconds: what the model wants, and small."""
    work.mkdir(parents=True, exist_ok=True)
    if (work / "split.ok").exists():
        return
    for old in work.glob("c*.wav"):
        old.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-vn", "-ac", "1", "-ar", "16000",
                    "-f", "segment", "-segment_time", str(CHUNK), str(work / "c%04d.wav")], check=True)
    (work / "split.ok").write_text("")


def transcribe_pieces(work, run_model):
    """run_model(wav) -> (duration seconds, [(start seconds, text)]). Saves each piece's result as it finishes."""
    for wav in sorted(work.glob("c*.wav")):
        done = wav.with_suffix(".json")
        if done.exists():
            continue
        duration, segs = run_model(wav)
        tmp = wav.with_suffix(".tmp")
        tmp.write_text(json.dumps({"duration": duration, "segs": segs}))
        tmp.replace(done)


def join(work):
    lines, offset = [], 0.0
    for done in sorted(work.glob("c*.json")):
        d = json.loads(done.read_text())
        lines += [f"{stamp(offset + s)} {t}" for s, t in d["segs"]]
        offset += d["duration"]
    return lines, offset


def one(f, target, work, run_model, label):
    split(f, work)
    transcribe_pieces(work, run_model)
    lines, duration = join(work)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    tmp.write_text(f"# {f.name}\n# {duration / 60:.0f} min, {label}\n" + "\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(target)
    shutil.rmtree(work)
    return duration


def read_wav(wav):
    """The 16 kHz mono piece as the float samples the model takes. Read here, not by faster-whisper's own loader:
    that goes through PyAV, and a new PyAV release (19) broke it, which stopped every transcription."""
    import wave
    import numpy as np
    with wave.open(str(wav), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def whisper(model_name, language, threads):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=threads)

    def run_model(wav):
        segs, info = model.transcribe(read_wav(wav), language=language, vad_filter=True, beam_size=1)
        return info.duration, [(s.start, s.text.strip()) for s in segs]
    return run_model


def main(argv):
    ap = argparse.ArgumentParser(description="Transcribe every audio/video file in a folder, offline.")
    ap.add_argument("source")
    ap.add_argument("out")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--language", default="en", help="language code, or 'auto' to detect")
    ap.add_argument("--threads", type=int, default=2, help="CPU threads (default 2, so the machine stays usable)")
    ap.add_argument("--only", help="only files whose path contains this text")
    a = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed: apt install ffmpeg / brew install ffmpeg / winget install ffmpeg")
    todo = [(f, out_path(f, a.source, a.out)) for f in files(a.source, a.only)]
    todo = [(f, t) for f, t in todo if not t.exists()]
    print(f"{len(todo)} file{'' if len(todo) == 1 else 's'} to transcribe", flush=True)
    if not todo:
        return
    run_model = whisper(a.model, None if a.language == "auto" else a.language, a.threads)
    for i, (f, target) in enumerate(todo, 1):
        work = Path(a.out) / ".work" / hashlib.sha1(str(f.resolve()).encode()).hexdigest()[:16]
        t0 = time.time()
        try:
            dur = one(f, target, work, run_model, f"model {a.model}")
        except subprocess.CalledProcessError:
            print(f"{i}/{len(todo)} SKIPPED {f}: ffmpeg could not read it", flush=True)
            continue
        print(f"{i}/{len(todo)} {target.name}: {dur / 60:.0f} min of audio in {(time.time() - t0) / 60:.1f} min",
              flush=True)
    work_root = Path(a.out) / ".work"
    if work_root.exists() and not any(work_root.iterdir()):
        work_root.rmdir()
    print("All done.", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
