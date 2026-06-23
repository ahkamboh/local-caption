#!/usr/bin/env python3
"""
local-caption — ONE command: video in, captioned video out.

    python caption.py myvideo.mp4

Captions are auto-sized and positioned to fit the video (proportional on any resolution),
English by default. It transcribes, force-aligns timing to the audio, and burns clean,
correctly-proportioned captions — no manual tweaking. Works even if your ffmpeg lacks
libass (it falls back to rendering captions with Pillow + the core overlay filter).

POWER OPTIONS (all optional):
    --lang en              caption language (default: en)
    --hinglish             mixed Hindi-English / code-switched audio
    --style clean|bold|tiktok|hormozi    look (default: clean)
    --pos bottom|center|top              placement (default: bottom)
    --size PCT             caption height as % of video height (default: 5)
    --font PATH            use a specific .ttf (otherwise a system font is auto-found)
    --srt                  only write a .srt (don't burn the video)
    --from-srt FILE        skip transcription; just burn an existing .srt (proportioned)
    --translate "hi,es"    also write translated .srt files
    --out FILE             output path (default: <video>.captioned.mp4)

Tip: it auto-runs itself with the bundled venv python, so plain `python caption.py video.mp4` works.
"""
import os
import sys
import re
import glob
import argparse
import subprocess
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# style -> knobs.  caps = uppercase; box = translucent pill (tiktok); stroke_mul = outline thickness.
STYLES = {
    "clean":   dict(caps=False, box=False, stroke_mul=1.0),
    "bold":    dict(caps=False, box=False, stroke_mul=1.7),
    "tiktok":  dict(caps=False, box=True,  stroke_mul=1.0),
    "hormozi": dict(caps=True,  box=False, stroke_mul=2.2),
}
ALIGN = {"bottom": 2, "center": 5, "top": 8}   # ASS numpad
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def ensure_venv():
    vpy = os.path.join(HERE, ".venv-whisperx", "Scripts" if os.name == "nt" else "bin",
                       "python.exe" if os.name == "nt" else "python")
    if os.path.exists(vpy) and os.path.abspath(sys.executable) != os.path.abspath(vpy):
        os.execv(vpy, [vpy, os.path.abspath(__file__)] + sys.argv[1:])


def _py(*parts):
    return [sys.executable, os.path.join(HERE, *parts)]


def probe_dims(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", video], capture_output=True, text=True)
    m = re.search(r"(\d+)x(\d+)", out.stdout.strip())
    if not m:
        sys.exit(f"!! couldn't read video dimensions from {video}")
    return int(m.group(1)), int(m.group(2))


def _srt_ts_to_sec(ts):
    ts = ts.strip().replace(".", ",")
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        tline = next((l for l in lines if "-->" in l), None)
        if not tline:
            continue
        a, b = tline.split("-->")
        text = " ".join(lines[lines.index(tline) + 1:]).strip()
        if text:
            cues.append((_srt_ts_to_sec(a), _srt_ts_to_sec(b), text))
    return cues


def has_libass():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return re.search(r"\bsubtitles\b", out.stdout) is not None


def find_font(user=None):
    if user and os.path.exists(user):
        return user
    bundled = glob.glob(os.path.join(HERE, "assets", "fonts", "*.ttf"))
    for c in bundled + FONT_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def _esc(p):
    return p.replace("\\", "/").replace(":", "\\:")


def _sec_to_ass(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{int(s):02d}.{int(round((s - int(s)) * 100)):02d}"


def burn_libass(video, cues, w, h, style, pos, size_pct, out):
    st = STYLES[style]
    fs = max(14, round(h * size_pct / 100.0))
    outline = max(1, round(h * 0.004 * st["stroke_mul"]))
    mv, mlr = round(h * 0.06), round(w * 0.06)
    border = 3 if st["box"] else 1
    back = "&HA0000000" if st["box"] else "&H00000000"
    head = ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
            "Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
            f"Style: Default,Arial,{fs},&H00FFFFFF,&H00000000,{back},1,{border},{outline},"
            f"{max(0, round(h * 0.0018))},{ALIGN[pos]},{mlr},{mlr},{mv}\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    rows = [f"Dialogue: 0,{_sec_to_ass(s)},{_sec_to_ass(e)},Default,,0,0,0,,{(t.upper() if st['caps'] else t)}"
            for s, e, t in cues]
    ass = os.path.join("work", "_cap.ass")
    open(ass, "w", encoding="utf-8").write(head + "\n".join(rows) + "\n")
    return subprocess.run(["ffmpeg", "-y", "-i", video, "-vf", f"subtitles={_esc(ass)}",
                           "-c:a", "copy", out]).returncode == 0


def burn_pillow(video, cues, w, h, style, pos, size_pct, font_path, out):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit("!! your ffmpeg has no libass, so captions are rendered with Pillow. Install it:\n"
                 "     pip install Pillow\n   (or reinstall ffmpeg with libass: brew install ffmpeg)")
    fp = find_font(font_path)
    if not fp:
        sys.exit("!! no usable font found — pass --font /path/to/font.ttf")
    st = STYLES[style]
    fs = max(14, round(h * size_pct / 100.0))
    stroke = max(1, round(fs * 0.07 * st["stroke_mul"]))
    font = ImageFont.truetype(fp, fs)
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    def tw(s):
        b = scratch.textbbox((0, 0), s, font=font, stroke_width=stroke)
        return b[2] - b[0]

    capdir = os.path.join("work", "_caps")
    shutil.rmtree(capdir, ignore_errors=True)
    os.makedirs(capdir, exist_ok=True)
    pngs, meta = [], []
    for i, (s, e, text) in enumerate(cues):
        if st["caps"]:
            text = text.upper()
        maxw = int(w * 0.88)
        words, lines, cur = text.split(), [], ""
        for word in words:
            cand = (cur + " " + word).strip()
            if not cur or tw(cand) <= maxw:
                cur = cand
            else:
                lines.append(cur); cur = word
        if cur:
            lines.append(cur)
        line_h = int(fs * 1.28)
        pad = int(fs * 0.4)
        cw = min(w, max((tw(l) for l in lines), default=1) + stroke * 2 + pad * 2)
        ch = line_h * len(lines) + stroke * 2 + pad
        img = Image.new("RGBA", (max(2, cw), max(2, ch)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if st["box"]:
            d.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=int(fs * 0.28), fill=(0, 0, 0, 165))
        y = (ch - line_h * len(lines)) // 2
        for l in lines:
            d.text(((cw - tw(l)) // 2, y), l, font=font, fill=(255, 255, 255, 255),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
            y += line_h
        p = os.path.join(capdir, f"c{i}.png")
        img.save(p)
        pngs.append(p); meta.append((s, e))
    if not pngs:
        sys.exit("!! no captions to burn.")
    mv = round(h * 0.06)
    ypos = {"bottom": f"H-h-{mv}", "center": "(H-h)/2", "top": f"{mv}"}[pos]
    ins = ["-i", video]
    for p in pngs:
        ins += ["-i", p]
    chains, last = [], "0:v"
    for i, (s, e) in enumerate(meta):
        lbl = f"v{i + 1}"
        chains.append(f"[{last}][{i + 1}:v]overlay=x=(W-w)/2:y={ypos}:"
                      f"enable='between(t,{s:.3f},{e:.3f})'[{lbl}]")
        last = lbl
    cmd = ["ffmpeg", "-y"] + ins + ["-filter_complex", ";".join(chains),
                                    "-map", f"[{last}]", "-map", "0:a?", "-c:a", "copy", out]
    return subprocess.run(cmd).returncode == 0


def main():
    ensure_venv()
    ap = argparse.ArgumentParser(description="local-caption — captions for any video, one command.")
    ap.add_argument("video")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--hinglish", action="store_true")
    ap.add_argument("--style", default="clean", choices=list(STYLES))
    ap.add_argument("--pos", default="bottom", choices=list(ALIGN))
    ap.add_argument("--size", type=float, default=5.0)
    ap.add_argument("--font", default=None)
    ap.add_argument("--srt", action="store_true")
    ap.add_argument("--from-srt", dest="from_srt", default=None)
    ap.add_argument("--translate", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"!! {tool} not found — install ffmpeg (brew/apt/winget install ffmpeg).")
    if not os.path.exists(a.video):
        sys.exit(f"!! no such file: {a.video}")

    os.makedirs("work", exist_ok=True)
    base = os.path.splitext(os.path.basename(a.video))[0]
    srt = a.from_srt

    if not srt:
        tj = os.path.join("work", f"{base}.transcript.json")
        cmd = _py("scripts", "align.py") + [a.video, "--out", tj]
        cmd += (["--code-switch", "--dual", "hi", "en"] if a.hinglish else ["--lang", a.lang])
        print(f"[local-caption] transcribing + aligning ({'hinglish' if a.hinglish else a.lang}) ...")
        if subprocess.run(cmd).returncode != 0 or not os.path.exists(tj):
            sys.exit("!! transcription failed. Run `python setup.py` first (installs the engine).")
        subprocess.run(_py("scripts", "export-subs.py") + [tj, "--out", os.path.join("work", base)], check=True)
        srt = os.path.join("work", f"{base}.srt")

    if a.translate:
        subprocess.run(_py("scripts", "multilang-subs.py") + [srt, "--to", a.translate], check=False)

    if a.srt:
        print(f"[local-caption] subtitles -> {srt}")
        return

    cues = parse_srt(srt)
    w, h = probe_dims(a.video)
    out = a.out or f"{base}.captioned.mp4"
    engine = "libass" if has_libass() else "pillow+overlay"
    print(f"[local-caption] burning '{a.style}' — {w}x{h}, {round(h * a.size / 100)}px, {a.pos} "
          f"({engine}) -> {out}")
    ok = (burn_libass(a.video, cues, w, h, a.style, a.pos, a.size, out) if has_libass()
          else burn_pillow(a.video, cues, w, h, a.style, a.pos, a.size, a.font, out))
    if not ok:
        sys.exit("!! burn failed.")
    print(f"[local-caption] done -> {out}")


if __name__ == "__main__":
    main()
