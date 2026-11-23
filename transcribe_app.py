#!/usr/bin/env python3
"""Transcribe Folder app: pick a folder of recordings, press Start, get a text file for each one.

  python3 transcribe_app.py

The window runs transcribe.py for you and shows its progress. Stop any time; Start again carries on where it
stopped. The speech model needs the faster-whisper package: if this Python doesn't have it, the window offers to
set it up in its own folder (~/.local/share/transcribe-folder), so nothing on your system changes.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from appkit import BG, FG, FONT, FROZEN, App, Page, handle_cli, open_path, script_cmd, write

ACCENT = "#0c8599"
HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "transcribe-folder" / "venv"
VPY = VENV / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
MODELS = [("base.en", "base.en: fast, good for clear English (recommended)"),
          ("tiny.en", "tiny.en: fastest, rougher"),
          ("small.en", "small.en: slower, more accurate English"),
          ("medium.en", "medium.en: slow, very accurate English"),
          ("large-v3", "large-v3: slowest, any language")]
ABOUT = ("Transcribe Folder\n\nEvery audio and video file in a folder becomes a text file with timestamps. "
         "Runs offline on your own computer; nothing is uploaded.\n\nFree and open source (MIT), by Sebayt Labs. "
         "Speech model: faster-whisper (OpenAI Whisper).")


def has_whisper(py):
    try:
        return subprocess.run([str(py), "-c", "import faster_whisper"], capture_output=True).returncode == 0
    except OSError:
        return False


def engine_python():
    if FROZEN:  # the download carries faster-whisper and runs transcribe.py itself
        return sys.executable
    if has_whisper(sys.executable):
        return sys.executable
    if VPY.exists() and has_whisper(VPY):
        return str(VPY)
    return None


class TranscribePage(Page):
    HELP = ("Transcribe\n\n1. Folder with recordings: the folder holding your audio or video (subfolders too).\n"
            "2. Save text to: where the .txt files go. The same subfolders are made there.\n"
            "3. Pick a model. base.en is right for most English recordings.\n4. Press Start.\n\n"
            "Stop whenever you like. Press Start again later and it picks up where it stopped; files already done "
            "are skipped.\n\nThe first run downloads the model once (about 150 MB for base.en).")
    HINT = "Pick the folder with your recordings, then press Start."

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.proc = None
        self.title("Transcribe a folder", "Every recording in a folder becomes a text file with timestamps. "
                                          "Offline: nothing leaves your computer.")
        self.steps(["Pick the folder with your recordings (audio or video, subfolders included).",
                    "Pick where the text files should go.",
                    "Press Start. Stop any time; Start again carries on where it stopped."])
        self.src = tk.StringVar()
        self.out = tk.StringVar(value=str(Path.home() / "Transcripts"))
        self.fields = tk.Frame(self.body, bg=BG)
        self.fields.pack(fill="x")
        self.path_field("Recordings folder", self.src, parent=self.fields)
        self.path_field("Save text to", self.out, parent=self.fields)
        r = self.model_row = self.row()
        tk.Label(r, text="Model", bg=BG, fg=FG, font=(FONT, 11), width=16, anchor="w").pack(side="left")
        self.model = ttk.Combobox(r, values=[d for _, d in MODELS], state="readonly", width=48)
        self.model.current(0)
        self.model.pack(side="left")
        r = self.buttons = self.row(pady=10)
        self.go = self.button(r, "Start", self.start)
        self.go.pack(side="left")
        self.stop_btn = self.button(r, "Stop", self.stop, primary=False, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.button(r, "Open the text folder", self.open_out, primary=False).pack(side="right")
        self.bar = ttk.Progressbar(self.body, mode="determinate")
        self.bar.pack(fill="x", pady=(4, 0))
        self.log = self.log_box(10)
        self.engine = engine_python()
        if not self.engine:
            write(self.log, "The speech model isn't set up yet. Press Start and it's set up first (a few minutes, "
                            "once).\n")

    def open_out(self):
        p = Path(self.out.get())
        p.mkdir(parents=True, exist_ok=True)
        open_path(p)

    def start(self):
        if not Path(self.src.get()).exists():
            messagebox.showinfo("Transcribe", "Pick the folder with your recordings first.")
            return
        if not shutil.which("ffmpeg"):
            messagebox.showerror("Transcribe", "ffmpeg is needed to read the recordings. Install it:\n"
                                               "Linux: sudo apt install ffmpeg\nMac: brew install ffmpeg\n"
                                               "Windows: winget install ffmpeg")
            return
        self.go.config(state="disabled")
        self.stop_btn.config(state="normal")
        model = MODELS[self.model.current()][0]
        args = (self.src.get(), self.out.get(), model)   # read here: Tk can't be touched from the worker thread
        threading.Thread(target=self.work, args=args, daemon=True).start()

    def say(self, text):
        self.after(0, lambda: write(self.log, text if text.endswith("\n") else text + "\n"))

    def work(self, src, out, model):
        if not self.engine:
            self.say("Setting up the speech model package (once)…")
            try:
                if shutil.which("uv"):
                    subprocess.run(["uv", "venv", "-q", str(VENV)], check=True)
                    subprocess.run(["uv", "pip", "install", "-q", "--python", str(VPY), "faster-whisper"], check=True)
                else:
                    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
                    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "faster-whisper"], check=True)
            except (subprocess.CalledProcessError, OSError) as e:
                self.say(f"Couldn't set it up ({e}). Install it yourself with:  pip install faster-whisper")
                self.after(0, self.finished)
                return
            self.engine = str(VPY)
            self.say("Set up. Starting.")
        args = [src, out, "--model", model, "--language", "auto" if model == "large-v3" else "en"]
        script = HERE / "transcribe.py"
        cmd = script_cmd(script, *args) if FROZEN else [self.engine, "-u", str(script), *args]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        total = None
        for line in self.proc.stdout:
            line = line.rstrip()
            if "HF_TOKEN" in line or not line:
                continue
            m = re.match(r"(\d+) files? to transcribe", line)
            if m:
                total = int(m.group(1))
                self.after(0, lambda t=total: self.bar.config(maximum=max(t, 1), value=0))
            m = re.match(r"(\d+)/(\d+) ", line)
            if m:
                self.after(0, lambda v=int(m.group(1)): self.bar.config(value=v))
            self.say(line)
        code = self.proc.wait()
        if code not in (0, None) and code > 0:
            self.say(f"Stopped with an error (code {code}). Start again to carry on.")
        self.after(0, self.finished)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.say("Stopped. Press Start to carry on from here.")

    def finished(self):
        self.proc = None
        self.go.config(state="normal")
        self.stop_btn.config(state="disabled")


def tutorial(app):
    pg = lambda: app.page("main")
    return [
        {"title": "Welcome to Transcribe Folder", "target": lambda: app.tour_button,
         "text": "Hours of lectures, calls or voice memos are hard to search and slow to review. This turns every "
                 "recording in a folder into a text file with a timestamp on each line. You can search it, skim it "
                 "and quote it. It runs on your own computer, offline. Nothing is uploaded.\n\nAbout two minutes.",
         "do": "click Next."},
        {"title": "Pick the folders", "target": lambda: pg().fields,
         "text": "Recordings folder: audio or video of any kind, subfolders included. Save text to: the text files "
                 "go here, in the same subfolders.",
         "do": "press Browse and pick a folder with a recording or two in it.",
         "check": lambda _: Path(pg().src.get()).is_dir()},
        {"title": "Pick a model", "target": lambda: pg().model_row,
         "text": "A bigger model is more accurate and slower. base.en suits clear English. large-v3 handles any "
                 "language. The model is downloaded once, the first time.",
         "do": "leave base.en unless you need another language. Click Next."},
        {"title": "Start, and stop any time", "target": lambda: pg().buttons,
         "text": "Long recordings are done in 20-minute pieces, and each piece is saved as it finishes. A laptop "
                 "with little memory doesn't run out, and if you stop (or the power goes), Start picks up where it "
                 "left off. Files already done are skipped.",
         "do": "click Start. The first time, it sets up the speech model before it begins.",
         "check": lambda _: str(pg().go.cget("state")) == "disabled" or pg().proc is not None},
        {"title": "You're ready", "target": lambda: pg().buttons,
         "text": "Leave it running. The bar shows how many files are done. 'Open the text folder' shows the results. "
                 "Each line starts with its time in the recording, so you can jump straight to that spot.\n\n"
                 "Press F1 for help.",
         "do": "click Done."},
    ]


def main():
    app = App("Transcribe Folder", "Recordings in, text out. Offline.", ACCENT, ABOUT, size="1000x700",
              class_name="TranscribeFolder")
    app.add_page("main", "Transcribe", TranscribePage)
    if (HERE / "icon.png").exists():
        app.iconphoto(True, tk.PhotoImage(file=str(HERE / "icon.png")))
    app.set_tutorial(lambda: tutorial(app), VENV.parent / "settings.json")
    app.run("main")


if __name__ == "__main__":
    handle_cli()
    main()
