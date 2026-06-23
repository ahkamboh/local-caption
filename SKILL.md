# local-caption — SKILL

You are an AI **captioning agent**. This repo adds **accurate, perfectly-timed captions/subtitles to any video or audio, in any language** (English by default), for both **speech and music**, with first-class **Hinglish / code-switched** support. Runs on **Windows, macOS, and Linux**.

Core principle: **words come from speech recognition, but TIMING comes from forced alignment on the waveform** — never raw ASR timestamps. So captions never drift early/late, even when the transcript has spelling errors.

## One-time setup (Windows / macOS / Linux)
Requires: **Python 3.10+**, `ffmpeg`, ~4 GB disk. (torch ships wheels through 3.14; if `whisperx` lacks a wheel on a brand-new Python, use 3.11–3.12.)
```bash
python setup.py        # cross-platform: creates ./.venv-whisperx and installs everything
# macOS/Linux convenience: bash setup.sh      ·      Windows convenience: setup.bat
```
ffmpeg: macOS `brew install ffmpeg` · Ubuntu `sudo apt install ffmpeg` · Windows `winget install ffmpeg`.
Models (Whisper `small`, MMS_FA, whisperX) auto-download on first run.

## Easiest path — the one-command wrapper (PREFER THIS)
For "caption this video" requests, just run the top-level wrapper. It does transcribe → align →
burn with **auto-proportioned** captions (correct size/spacing/alignment for any resolution), and
falls back to a libass-free renderer (Pillow + `overlay`) if the user's ffmpeg has no subtitle support:
```
python caption.py <video>                                  # English, clean, proportioned -> <video>.captioned.mp4
python caption.py <video> --hinglish --style tiktok        # Hinglish + TikTok box
python caption.py <video> --lang ur --pos center --size 6  # other language / placement / size
python caption.py <video> --srt                            # just write a .srt (no burn)
python caption.py <video> --from-srt FILE                  # burn an existing .srt, proportioned
```
15 styles (bundled fonts): `clean` (default) `bold` `hormozi` `green` `beast` `impact` `bebas` `tiktok`
`pill` `boxed` `yellow` `neon` `gradient` `minimal` `subtitle`. Drop to the individual scripts below
only when you need the raw transcript, custom rendering, or translation.

**Best accuracy:** add `--accurate` (uses `openai/whisper-large-v3`). The Hinglish path already uses
large-v3. Pre-fetch it once with `python setup.py --large` (otherwise it downloads on first `--accurate`).

**Custom style — build ANY look the user describes.** Map the user's words to these flags (they override
`--style`):
- `--font <name|path>` — a bundled font (`Poppins-Bold`, `Poppins-Black`, `Anton-Regular`, `BebasNeue-Regular`, `ArchivoBlack-Regular`) or any `.ttf` path
- `--fill #hex` (text colour) · `--outline #hex` · `--box #hex|#hexAA|none` (pill behind text)
- `--caps` / `--no-caps` · `--gradient "#hex,#hex,#hex"` · `--glow` · `--ow N` (outline thickness)
- `--size <pct>` (height) · `--pos bottom|center|top`

Example — user says *"hot-pink caps in a dark rounded box, big, Anton font"* →
```
python caption.py v.mp4 --fill "#ff3da6" --box "#10141ae0" --caps --font Anton-Regular.ttf --size 6
```
To make a brand-new **named** style permanent, add an entry to the `STYLES` dict in `caption.py`.

## Always run scripts with the venv's python — written here as `PY`:
- **macOS / Linux:** `PY` = `./.venv-whisperx/bin/python`
- **Windows:** `PY` = `.venv-whisperx\Scripts\python`

## The scripts
- `transcribe.py` — Whisper → word-level transcript (English default; `--lang xx` for others).
- `align.py` — **forced alignment** for frame-accurate timing. `--code-switch` for Hinglish/mixed.
- `cs_transcribe.py` — code-switch-robust word recognition (per-segment language ID).
- `mms_align.py` — universal MMS_FA forced aligner (1100+ languages, any script).
- `validate_timing.py` — timing sanity-check used by the code-switch path.
- `export-subs.py` — transcript → `.srt` + `.vtt`.
- `multilang-subs.py` — translate subtitles into many languages, **offline**.
- `caption.py` — all-in-one **styled** captions (karaoke/word/line; Hormozi/TikTok/neon…) → animated `captions.js`.

## Caption a video (the main job) — default language = English
For another language pass `--lang <code>`. For **Hinglish / mixed** use `--code-switch`.

### 1) Frame-accurate word timings
Speech (talking, podcast, UGC):
```
PY scripts/align.py INPUT --lang en --out work/transcript.json
```
Hinglish / mixed Hindi-English (or any code-switched audio):
```
PY scripts/align.py INPUT --code-switch --dual hi en --out work/transcript.json
```
Any other language (Urdu, Spanish, Arabic, Chinese, …):
```
PY scripts/align.py INPUT --lang ur --out work/transcript.json
```

### 2a) Subtitles (.srt / .vtt) + burn into the video
```
PY scripts/export-subs.py work/transcript.json --out work/subs
ffmpeg -i INPUT -vf "subtitles=work/subs.srt" -c:a copy captioned.mp4
```
The `.srt` is also perfect to upload to YouTube directly (selectable + SEO).

### 2b) Styled / animated captions (Hormozi, TikTok, karaoke — short-form)
```
PY scripts/caption.py INPUT --lang en --content speech --style karaoke --preset hormozi --out out/
```
Presets: `hormozi`, `beast`, `pill`, `neon`, `gradient`, `minimal`, `tiktok`. Use `--content music` for songs/lyrics. See `docs/caption-styles.md`.

### 3) Translate captions into any language (optional)
```
PY scripts/multilang-subs.py work/subs.srt --to "hi,ur,es,fr,ar,de" [--burn INPUT]
```

## Rules (baked in — do not override)
- Timing is ALWAYS forced alignment, never raw ASR timestamps (no lead/lag).
- **Default caption language = English**; pass `--lang` for anything else.
- Music/singing → `--content music`; speech/talking → `--content speech`.
- Run **every** script with `PY` (the venv python) so it has whisperx/torch.
- Before delivering, spot-check a few captions at their word onsets to confirm sync.

## Language codes
`en` (default), `hi`, `ur`, `pa`, `es`, `fr`, `de`, `pt`, `ar`, `zh`, `ja`, `ko`, `ru`, `it`, `tr`, `id`, `nl`, `pl`, `uk`, … — Whisper supports ~99 languages; MMS_FA aligns 1100+.
