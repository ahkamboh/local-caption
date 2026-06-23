# local-caption — add captions to any video, in any language, for any AI agent

**Free & open-source captioning that any AI agent can run — on Windows, macOS, and Linux.** Add accurate, perfectly-timed captions / subtitles to **any video or song**, in **any language** (English by default), for both **speech and music** — with first-class **Hinglish / code-switched** support. Words come from speech recognition; **timing comes from forced alignment on the waveform**, so captions never drift early or late.

> Built for **Claude Code, Cursor, Codex, Grok**, and any IDE/agent. Point your agent at this repo and ask it to caption your video.

## ⚡ Easiest way — ONE command

```bash
python caption.py myvideo.mp4
```

That's it. It transcribes, aligns the timing to the audio, and burns clean captions that are **auto-sized and positioned to fit the video** (proportional on any resolution — landscape *or* vertical), English by default → `myvideo.captioned.mp4`. No styling, no tweaking. Works even if your ffmpeg lacks libass (it falls back to rendering captions and compositing them with the core `overlay` filter).

**Power users** — same command, optional flags:
```bash
python caption.py reel.mp4 --hinglish --style tiktok     # Hinglish + TikTok box look
python caption.py talk.mp4 --style hormozi --pos center  # big bold caps, centered
python caption.py clip.mp4 --lang ur --size 6            # Urdu, slightly larger
python caption.py vid.mp4  --srt                         # just write the .srt, no burn
python caption.py vid.mp4  --from-srt my.srt             # burn an existing .srt, proportioned
```

## ⚡ Setup — paste this into your AI agent

Clone the repo, open it in your agent (Claude Code / Cursor / Codex / Grok / any), then paste:

```
You are a captioning agent. Read ./SKILL.md in this repo and follow it exactly.

Goal: add accurate, perfectly-timed captions to the video or audio I give you,
in any language (default: English; tell me if it's different; Hinglish supported),
for both speech AND music.

Do this:
1. run `python setup.py` if ./.venv-whisperx isn't set up yet
2. ask me for: the media file path + the caption language (default = English)
3. get frame-accurate word timings with forced alignment
   (scripts/align.py; add --code-switch for Hinglish/mixed) — run scripts with the venv python
4. export an .srt and burn the captions into the video with ffmpeg
5. show me the output file paths

Start by reading SKILL.md, then ask me for the file path.
```

## Quick start per agent
- **Claude Code** — open the folder; it auto-reads `CLAUDE.md`. Just say *"caption ./myvideo.mp4"*.
- **Cursor** — auto-reads `.cursorrules`. Say *"caption ./reel.mp4 in hinglish"*.
- **Codex** — auto-reads `AGENTS.md`. Same.
- **Grok / ChatGPT / any chat agent** — paste the setup prompt above + the contents of `SKILL.md`.

## Requirements
- **Python 3.10+** — torch supports 3.14; if `whisperx` lacks a wheel on a brand-new version, use 3.11–3.12
- **ffmpeg** — macOS `brew install ffmpeg` · Ubuntu `sudo apt install ffmpeg` · Windows `winget install ffmpeg`
- ~4 GB disk for models (auto-download on first run)

## Run it yourself (no agent)
Set up once, then call scripts with the venv's python.

```bash
python setup.py        # creates ./.venv-whisperx and installs everything (Win/Mac/Linux)
```

`PY` below = the venv python:
**macOS/Linux** `./.venv-whisperx/bin/python` · **Windows** `.venv-whisperx\Scripts\python`

```bash
# speech, English (default):
PY scripts/align.py video.mp4 --lang en --out work/transcript.json
PY scripts/export-subs.py work/transcript.json --out work/subs
ffmpeg -i video.mp4 -vf "subtitles=work/subs.srt" -c:a copy captioned.mp4

# Hinglish / mixed Hindi-English:
PY scripts/align.py video.mp4 --code-switch --dual hi en --out work/transcript.json

# translate captions into many languages (offline):
PY scripts/multilang-subs.py work/subs.srt --to "hi,ur,es,fr,ar"

# styled TikTok / Hormozi animated captions:
PY scripts/caption.py video.mp4 --lang en --content speech --style karaoke --preset hormozi --out out/
```

## What it does
- captions in **any language** — English by default, **Hinglish / code-switched** first-class, 1100+ languages aligned (MMS_FA)
- works on **speech and music / lyrics**
- **forced alignment** = frame-accurate timing, never early or late
- outputs **.srt / .vtt** (great for YouTube — selectable + SEO), a burned-in video, or animated styled captions
- famous looks built in: **Hormozi, MrBeast, TikTok, neon, karaoke** (`scripts/caption.py`)
- translate subtitles into 30+ languages, fully **offline**
- runs on **Windows, macOS, Linux** · 100% local · free · **MIT**

## How it works
1. **Words** — Whisper / faster-whisper transcribes the audio (per-segment language ID handles code-switching like Hinglish).
2. **Timing** — those words are force-aligned to the waveform (whisperX for 40+ languages, MMS_FA for 1100+). Timing comes from the audio, not the spelling — so text errors never cause drift.
3. **Output** — `.srt` / `.vtt`, a burned-in video, or an animated `captions.js` for motion graphics.

## License
MIT — free for anyone, including AI agents. Built by [Ali Hamza Kamboh](https://alihamzakamboh.com).
