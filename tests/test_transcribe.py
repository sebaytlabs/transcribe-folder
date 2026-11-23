"""python3 -m unittest discover tests   (uses ffmpeg, no model download: a fake model stands in)"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import transcribe as t  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class Pieces(unittest.TestCase):
    def test_long_file_in_pieces_with_true_timestamps_and_resume(self):
        d = Path(tempfile.mkdtemp())
        src = d / "in" / "talks" / "a talk.mp3"
        src.parent.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=7", str(src)], check=True)
        t.CHUNK = 3                      # 7 s -> pieces of 3 + 3 + 1
        calls = []

        def fake(wav):
            calls.append(wav.name)
            if len(calls) == 2:
                raise KeyboardInterrupt  # stopped half way
            return 3.0, [(1.0, f"piece {wav.stem}")]
        target = t.out_path(src, d / "in", d / "out")
        self.assertEqual(target, d / "out" / "talks" / "a talk.txt")
        work = d / "out" / ".work" / "x"
        with self.assertRaises(KeyboardInterrupt):
            t.one(src, target, work, fake, "fake")
        self.assertTrue((work / "c0000.json").exists())
        calls.clear()
        t.one(src, target, work, lambda w: (calls.append(w.name), (3.0, [(1.0, f"piece {w.stem}")]))[1], "fake")
        self.assertNotIn("c0000.wav", calls, "a finished piece must not run again")
        text = target.read_text().splitlines()
        self.assertEqual(text[2:], ["[0:00:01] piece c0000", "[0:00:04] piece c0001", "[0:00:07] piece c0002"])
        self.assertFalse(work.exists())

    def test_files_and_only(self):
        d = Path(tempfile.mkdtemp())
        for n in ("a/x.MP3", "b/y.mkv", "c/z.txt"):
            (d / n).parent.mkdir(parents=True, exist_ok=True)
            (d / n).write_bytes(b"")
        self.assertEqual([p.name for p in t.files(d)], ["x.MP3", "y.mkv"])
        self.assertEqual([p.name for p in t.files(d, "B/")], ["y.mkv"])

    def test_stamp(self):
        self.assertEqual(t.stamp(3735), "[1:02:15]")


if __name__ == "__main__":
    unittest.main()


try:
    import numpy  # noqa: F401  (comes with faster-whisper)
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class ReadWav(unittest.TestCase):
    def test_pieces_are_read_as_float_samples_without_pyav(self):
        import struct
        import wave
        p = Path(tempfile.mkdtemp()) / "c0000.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<3h", 0, 16384, -32768))
        self.assertEqual(t.read_wav(p).tolist(), [0.0, 0.5, -1.0])
