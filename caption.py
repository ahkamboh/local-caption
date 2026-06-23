#!/usr/bin/env python3
"""
local-caption — ONE command: video in, captioned video out.

    python caption.py myvideo.mp4

Captions are auto-sized and positioned to fit the video (proportional on any resolution),
English by default, with famous caption looks + bundled fonts. It transcribes, force-aligns
timing to the audio, and burns clean, correctly-proportioned captions — no manual tweaking.
Renders with Pillow + ffmpeg's core `overlay`, so it works even if your ffmpeg lacks libass.

OPTIONS (all optional):
    --style NAME    one of 15 looks (default: clean). See the list below.
    --lang en       caption language (default: en)
    --hinglish      mixed Hindi-English / code-switched audio
    --pos bottom|center|top
    --size PCT      override caption height as % of video height
    --font PATH     use a specific .ttf (otherwise the style's bundled font)
    --srt           only write a .srt (don't burn)
    --from-srt FILE skip transcription; burn an existing .srt (proportioned)
    --translate "hi,es"   also write translated .srt files
    --out FILE      output path (default: <video>.captioned.mp4)

STYLES: clean bold hormozi green beast impact bebas tiktok pill boxed yellow neon gradient minimal subtitle
"""
import os
import sys
import re
import glob
import argparse
import subprocess
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "assets", "fonts")

# Famous caption looks. font = bundled file (None = system). fill/outline = RGB.
# ow = outline thickness mul. box = RGBA pill behind text (or None). caps = UPPERCASE.
# grad = vertical gradient fill [RGB,...] (overrides fill). glow = soft neon halo.
STYLES = {
    "clean":    dict(font="Poppins-Bold.ttf",        size=5.0, fill=(255, 255, 255), outline=(0, 0, 0), ow=1.0, box=None, caps=False, grad=None, glow=False),
    "bold":     dict(font="Poppins-Black.ttf",       size=5.0, fill=(255, 255, 255), outline=(0, 0, 0), ow=1.7, box=None, caps=False, grad=None, glow=False),
    "hormozi":  dict(font="Anton-Regular.ttf",       size=5.6, fill=(255, 255, 255), outline=(0, 0, 0), ow=2.1, box=None, caps=True,  grad=None, glow=False),
    "green":    dict(font="Anton-Regular.ttf",       size=5.6, fill=(59, 255, 106),  outline=(0, 0, 0), ow=2.1, box=None, caps=True,  grad=None, glow=False),
    "beast":    dict(font="Anton-Regular.ttf",       size=6.2, fill=(255, 214, 10),  outline=(0, 0, 0), ow=2.3, box=None, caps=True,  grad=None, glow=False),
    "impact":   dict(font="ArchivoBlack-Regular.ttf", size=5.4, fill=(255, 255, 255), outline=(0, 0, 0), ow=2.4, box=None, caps=True,  grad=None, glow=False),
    "bebas":    dict(font="BebasNeue-Regular.ttf",   size=6.6, fill=(255, 255, 255), outline=(0, 0, 0), ow=1.6, box=None, caps=True,  grad=None, glow=False),
    "tiktok":   dict(font="Poppins-Bold.ttf",        size=4.8, fill=(255, 255, 255), outline=(0, 0, 0), ow=0.0, box=(0, 0, 0, 165),    caps=False, grad=None, glow=False),
    "pill":     dict(font="Poppins-Bold.ttf",        size=4.8, fill=(17, 17, 17),    outline=(0, 0, 0), ow=0.0, box=(255, 214, 10, 235), caps=True, grad=None, glow=False),
    "boxed":    dict(font="Poppins-Bold.ttf",        size=4.5, fill=(255, 255, 255), outline=(0, 0, 0), ow=0.0, box=(0, 0, 0, 230),    caps=False, grad=None, glow=False),
    "yellow":   dict(font="Poppins-Bold.ttf",        size=5.0, fill=(255, 224, 77),  outline=(0, 0, 0), ow=1.4, box=None, caps=False, grad=None, glow=False),
    "neon":     dict(font="Poppins-Bold.ttf",        size=5.0, fill=(57, 230, 255),  outline=(2, 8, 28), ow=1.0, box=None, caps=False, grad=None, glow=True),
    "gradient": dict(font="Poppins-Black.ttf",       size=5.4, fill=(255, 255, 255), outline=(0, 0, 0), ow=1.6, box=None, caps=False, grad=[(92, 255, 208), (63, 169, 255), (123, 92, 255)], glow=False),
    "minimal":  dict(font="Poppins-Bold.ttf",        size=3.7, fill=(255, 255, 255), outline=(0, 0, 0), ow=0.7, box=None, caps=False, grad=None, glow=False),
    "subtitle": dict(font="Poppins-Bold.ttf",        size=4.2, fill=(255, 255, 255), outline=(0, 0, 0), ow=0.9, box=None, caps=False, grad=None, glow=False),
}
ALIGN = {"bottom": 2, "center": 5, "top": 8}
SYS_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
]


def ensure_venv():
    vpy = os.path.join(HERE, ".venv-whisperx", "Scripts" if os.name == "nt" else "bin",
                       "python.exe" if os.name == "nt" else "python")
    if os.path.exists(vpy) and os.path.abspath(sys.executable) != os.path.abspath(vpy):
        os.execv(vpy, [vpy, os.path.abspath(__file__)] + sys.argv[1:])


def _py(*p):
    return [sys.executable, os.path.join(HERE, *p)]


def probe_dims(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video],
                         capture_output=True, text=True)
    m = re.search(r"(\d+)x(\d+)", out.stdout.strip())
    if not m:
        sys.exit(f"!! couldn't read video dimensions from {video}")
    return int(m.group(1)), int(m.group(2))


def _ts(t):
    t = t.strip().replace(".", ",")
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    cues = []
    for blk in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip()):
        lines = [l for l in blk.splitlines() if l.strip()]
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = tl.split("-->")
        txt = " ".join(lines[lines.index(tl) + 1:]).strip()
        if txt:
            cues.append((_ts(a), _ts(b), txt))
    return cues


def find_font(preferred=None, user=None):
    if user:                                  # --font accepts a path OR a bundled font name
        if os.path.exists(user):
            return user
        p = os.path.join(FONTS, user)
        if os.path.exists(p):
            return p
        p2 = os.path.join(FONTS, user + ".ttf")
        if os.path.exists(p2):
            return p2
    if preferred:
        p = os.path.join(FONTS, preferred)
        if os.path.exists(p):
            return p
    for p in sorted(glob.glob(os.path.join(FONTS, "*.ttf"))):
        return p
    for c in SYS_FONTS:
        if os.path.exists(c):
            return c
    return None


def _hex(s):
    s = s.strip().lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in range(0, min(len(s), 8), 2))


def _box(s):
    if s is None or s.strip().lower() in ("none", "off", ""):
        return None
    c = _hex(s)
    return c if len(c) == 4 else (c[0], c[1], c[2], 235)   # default ~opaque if no alpha given


def _vgrad(Image, w, h, stops):
    img = Image.new("RGBA", (w, h))
    px = img.load()
    n = max(1, len(stops) - 1)
    for y in range(h):
        t = y / max(1, h - 1) * n
        i = min(int(t), n - 1)
        f = t - i
        c0, c1 = stops[i], stops[i + 1]
        col = tuple(int(c0[k] + (c1[k] - c0[k]) * f) for k in range(3)) + (255,)
        for x in range(w):
            px[x, y] = col
    return img


def render_caption(text, vw, fs, st, font_path, out_png, PIL):
    Image, ImageDraw, ImageFont, ImageFilter = PIL
    if st["caps"]:
        text = text.upper()
    font = ImageFont.truetype(font_path, fs)
    stroke = max(1, round(fs * 0.07 * st["ow"])) if st["ow"] > 0 else 0
    scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))

    def tw(s, sw=0):
        b = scratch.textbbox((0, 0), s, font=font, stroke_width=sw)
        return b[2] - b[0]

    maxw = int(vw * 0.86)
    words, lines, cur = text.split(), [], ""
    for word in words:
        cand = (cur + " " + word).strip()
        if not cur or tw(cand, stroke) <= maxw:
            cur = cand
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)

    line_h = int(fs * 1.22)
    text_w = max((tw(l, stroke) for l in lines), default=1)
    bpad = int(fs * 0.45) if st["box"] else int(fs * 0.2)
    cw = min(vw, text_w + stroke * 2 + bpad * 2)
    ch = line_h * len(lines) + stroke * 2 + bpad * 2
    img = Image.new("RGBA", (max(2, cw), max(2, ch)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if st["box"]:
        d.rounded_rectangle([0, 0, cw - 1, ch - 1], radius=int(fs * 0.3), fill=tuple(st["box"]))

    y0 = (ch - line_h * len(lines)) // 2
    if st["glow"]:
        gl = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        y = y0
        for l in lines:
            gd.text(((cw - tw(l)) // 2, y), l, font=font, fill=tuple(st["fill"]) + (255,))
            y += line_h
        img.alpha_composite(gl.filter(ImageFilter.GaussianBlur(max(2, int(fs * 0.22)))))

    y = y0
    for l in lines:
        x = (cw - tw(l, stroke)) // 2
        base = tuple(st["outline"]) if st["grad"] else tuple(st["fill"])
        d.text((x, y), l, font=font, fill=base + (255,),
               stroke_width=stroke, stroke_fill=tuple(st["outline"]) + (255,))
        y += line_h

    if st["grad"]:
        grad = _vgrad(Image, cw, ch, st["grad"])
        gmask = Image.new("L", (cw, ch), 0)
        gm = ImageDraw.Draw(gmask)
        y = y0
        for l in lines:
            gm.text(((cw - tw(l)) // 2, y), l, font=font, fill=255)
            y += line_h
        img.paste(grad, (0, 0), gmask)

    img.save(out_png)
    return cw, ch


def burn(video, cues, w, h, st, pos, size_pct, user_font, out):
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError:
        sys.exit("!! captions are rendered with Pillow — install it:  pip install Pillow")
    fs = max(14, round(h * (size_pct if size_pct else st["size"]) / 100.0))
    fp = find_font(st["font"], user_font)
    if not fp:
        sys.exit("!! no font found — pass --font /path/to/font.ttf")
    capdir = os.path.join("work", "_caps")
    shutil.rmtree(capdir, ignore_errors=True)
    os.makedirs(capdir, exist_ok=True)
    pngs, meta = [], []
    for i, (s, e, text) in enumerate(cues):
        p = os.path.join(capdir, f"c{i}.png")
        render_caption(text, w, fs, st, fp, p, (Image, ImageDraw, ImageFont, ImageFilter))
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
    ap.add_argument("--style", default="clean", choices=list(STYLES))
    ap.add_argument("--lang", default="en")
    ap.add_argument("--hinglish", action="store_true")
    ap.add_argument("--pos", default="bottom", choices=list(ALIGN))
    ap.add_argument("--size", type=float, default=0.0, help="override caption height %% of video height")
    ap.add_argument("--font", default=None, help="bundled font name or path to a .ttf")
    ap.add_argument("--model", default="small", choices=["small", "medium", "large-v3"],
                    help="ASR model. small = fast (default); large-v3 = best accuracy (~3GB, slower)")
    ap.add_argument("--accurate", action="store_true", help="use openai/whisper-large-v3 (best quality)")
    # --- custom style: describe ANY look; these override the chosen --style ---
    ap.add_argument("--fill", default=None, help="text colour, e.g. #ff2e88")
    ap.add_argument("--outline", default=None, help="outline colour, e.g. #000000")
    ap.add_argument("--box", default=None, help="box colour #RRGGBB / #RRGGBBAA, or 'none'")
    ap.add_argument("--caps", dest="caps", action="store_const", const=True, default=None)
    ap.add_argument("--no-caps", dest="caps", action="store_const", const=False)
    ap.add_argument("--gradient", default=None, help="gradient fill, e.g. '#5cffd0,#3fa9ff,#7b5cff'")
    ap.add_argument("--glow", dest="glow", action="store_const", const=True, default=None)
    ap.add_argument("--no-glow", dest="glow", action="store_const", const=False)
    ap.add_argument("--ow", type=float, default=None, help="outline thickness multiplier")
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
    model = "large-v3" if a.accurate else a.model

    os.makedirs("work", exist_ok=True)
    base = os.path.splitext(os.path.basename(a.video))[0]
    srt = a.from_srt
    if not srt:
        tj = os.path.join("work", f"{base}.transcript.json")
        cmd = _py("scripts", "align.py") + [a.video, "--out", tj, "--model", model]
        cmd += (["--code-switch", "--dual", "hi", "en"] if a.hinglish else ["--lang", a.lang])
        print(f"[local-caption] transcribing + aligning ({'hinglish' if a.hinglish else a.lang}, {model}) ...")
        if subprocess.run(cmd).returncode != 0 or not os.path.exists(tj):
            sys.exit("!! transcription failed. Run `python setup.py` first (installs the engine + model).")
        subprocess.run(_py("scripts", "export-subs.py") + [tj, "--out", os.path.join("work", base)], check=True)
        srt = os.path.join("work", f"{base}.srt")

    if a.translate:
        subprocess.run(_py("scripts", "multilang-subs.py") + [srt, "--to", a.translate], check=False)
    if a.srt:
        print(f"[local-caption] subtitles -> {srt}")
        return

    # effective style = chosen preset + any custom overrides (so users can describe any look)
    st = dict(STYLES[a.style])
    if a.fill:
        st["fill"] = _hex(a.fill)[:3]
    if a.outline:
        st["outline"] = _hex(a.outline)[:3]
    if a.box is not None:
        st["box"] = _box(a.box)
    if a.caps is not None:
        st["caps"] = a.caps
    if a.glow is not None:
        st["glow"] = a.glow
    if a.gradient:
        st["grad"] = [_hex(c)[:3] for c in a.gradient.split(",") if c.strip()]
    if a.ow is not None:
        st["ow"] = a.ow

    cues = parse_srt(srt)
    w, h = probe_dims(a.video)
    out = a.out or f"{base}.captioned.mp4"
    fs = round(h * (a.size if a.size else st["size"]) / 100.0)
    print(f"[local-caption] burning '{a.style}' — {w}x{h}, {fs}px, {a.pos} -> {out}")
    if not burn(a.video, cues, w, h, st, a.pos, a.size, a.font, out):
        sys.exit("!! burn failed.")
    print(f"[local-caption] done -> {out}")


if __name__ == "__main__":
    main()
