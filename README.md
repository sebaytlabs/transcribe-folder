# Transcribe Folder

Point it at a folder of lectures, podcasts, courses or voice memos. Every audio and video file in it becomes a text file with timestamps:

```
[0:00:00] Welcome back. Last week we covered the basics of compound interest.
[0:00:04] Today we'll look at what happens when you add a little every month,
[0:00:09] and why starting early matters more than the amount.
```

- **Private.** It runs offline on your own computer. Nothing is uploaded, and there's no account.
- **Fine on a small laptop.** Each file is cut into 20-minute pieces, so even a 3-hour video never has to fit in memory. It uses 2 CPU threads by default, so the computer stays usable.
- **Resumable.** Each piece is saved as it finishes. Stop it with Ctrl-C, a reboot or a flat battery, and the next run carries on from that piece. Finished files are skipped.
- **True timestamps.** `[1:02:15]` means 1 hour 2 minutes 15 seconds into the whole file, not into the piece.
- **Same layout.** The output mirrors your folders, so `course/week 3/lecture.mp4` becomes `out/week 3/lecture.txt`.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper), an efficient version of OpenAI's Whisper speech model.

## The app

```
python3 transcribe_app.py
```

Pick the folder with your recordings and where the text should go, choose a model, and press **Start**. A progress bar and a log show where it is. **Stop** works any time, and **Start** carries on from there.

If the speech model package isn't installed, the app sets it up the first time in its own folder (`~/.local/share/transcribe-folder`), so nothing on your system changes.

## From the command line

```
pip install faster-whisper            # plus ffmpeg: apt install ffmpeg / brew install ffmpeg / winget install ffmpeg
python3 transcribe.py ~/Courses/Spanish ~/Transcripts/Spanish
python3 transcribe.py ~/Podcasts ~/Transcripts --model small.en --only "2026"
python3 transcribe.py talk.mp4 ~/Transcripts --language auto --model large-v3
```

| Option | Default | |
|---|---|---|
| `--model` | `base.en` | `tiny.en` is fastest; `small.en` and `medium.en` are more accurate. `large-v3` handles any language. |
| `--language` | `en` | a language code, or `auto` to detect it |
| `--threads` | `2` | more threads run faster but leave less for everything else |
| `--only TEXT` | | only the files whose path contains TEXT |

On a two-core laptop, `base.en` runs several times faster than real time. The model downloads once on first use.

## Big jobs: pause when memory runs low (Linux)

Run the transcriber as a user service with a memory cap. Then let `memguard.sh` stop it when other programs need the memory, and start it again when the memory is free:

```
systemd-run --user --unit transcribe -p MemoryMax=2G \
  python3 ~/transcribe-folder/transcribe.py ~/Courses ~/Transcripts
~/transcribe-folder/memguard.sh transcribe 300 1700 &
```

The job pauses if free memory stays under 300 MB for a minute, and resumes once more than 1.7 GB is free. Because the transcriber is resumable, a pause costs at most one 20-minute piece.

## Tests

```
python3 -m unittest discover tests     # needs ffmpeg; uses a stand-in for the model
```

## License

MIT. Made by [Sebayt Labs](https://sebaytlabs.com).
