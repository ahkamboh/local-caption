#!/usr/bin/env python3
"""
footprint.py — render a "caption footprint": ONE SVG that shows the whole video's
caption health at a glance, so you can see WHERE captions are good vs weak without
watching. Pure code — no LLM, no tokens — and 100% faithful to the measured data.

Reads a word-level transcript (work/<base>.transcript.json → [{text,start,end,score}])
+ the video duration (ffprobe), and writes <out>.svg:
  • a confidence strip: each word a block on the timeline, colored by its forced-align
    score (green = solid · amber = check · red = likely wrong); blank = a gap (no caption)
  • gap markers for silences / missed speech > 2s
  • a time axis, a one-line stats readout, and a pass/check/fail verdict

Usage: python scripts/footprint.py work/<base>.transcript.json --video INPUT --out x.svg
"""
import sys, os, json, argparse, subprocess

W, H = 1000, 230
PAD = 24
TRACK_Y, TRACK_H = 80, 46
GAP_FLAG = 2.0
HI, MID, LO, NEU = "#1f9d57", "#e0a020", "#d8453a", "#9aa0a6"   # solid / check / wrong / unknown
TRACK, INK, MUTE = "#eceef1", "#2b2d31", "#8a8f98"


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def ffduration(video):
    if not video:
        return 0.0
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nk=1:nw=1", video], capture_output=True, text=True).stdout
        return float(out.strip() or 0)
    except Exception:
        return 0.0


def fmt(x):
    x = int(round(x))
    return f"{x // 60}:{x % 60:02d}"


def col(s):
    if s is None:
        return NEU
    if s >= 0.6:
        return HI
    if s >= 0.45:
        return MID
    return LO


def main():
    ap = argparse.ArgumentParser(description="render a caption footprint SVG (caption health at a glance)")
    ap.add_argument("transcript", help="work/<base>.transcript.json (word list with scores)")
    ap.add_argument("--video", default=None, help="source media (for duration via ffprobe)")
    ap.add_argument("--duration", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    words = [w for w in json.load(open(a.transcript, encoding="utf-8"))
             if w.get("start") is not None and w.get("end") is not None]
    if not words:
        sys.exit("[footprint] no timed words in transcript — nothing to draw.")
    dur = a.duration or ffduration(a.video) or max(w["end"] for w in words)
    out = a.out or (os.path.splitext(a.transcript)[0] + ".footprint.svg")

    def X(t):
        return PAD + max(0.0, min(1.0, t / dur)) * (W - 2 * PAD)

    blocks = []
    for w in words:
        x1, x2 = X(w["start"]), X(w["end"])
        sc = w.get("score")
        conf = ("%.2f" % sc) if sc is not None else "n/a"
        blocks.append(
            f'<rect x="{x1:.1f}" y="{TRACK_Y}" width="{max(1.2, x2 - x1):.1f}" height="{TRACK_H}" rx="1.5" '
            f'fill="{col(sc)}"><title>{esc(w.get("text"))} @{fmt(w["start"])} · conf {conf}</title></rect>')

    sw = sorted(words, key=lambda w: w["start"])
    gaps, biggest = [], 0.0
    for i in range(len(sw) - 1):
        g = sw[i + 1]["start"] - sw[i]["end"]
        biggest = max(biggest, g)
        if g > GAP_FLAG:
            gx, gw = X(sw[i]["end"]), X(sw[i + 1]["start"]) - X(sw[i]["end"])
            gaps.append(f'<rect x="{gx:.1f}" y="{TRACK_Y}" width="{max(2, gw):.1f}" height="{TRACK_H}" '
                        f'fill="none" stroke="{MUTE}" stroke-dasharray="3 2" stroke-width="1"/>')
            gaps.append(f'<text x="{gx + gw / 2:.1f}" y="{TRACK_Y - 6}" text-anchor="middle" '
                        f'font-size="10" fill="{MUTE}">{g:.0f}s gap</text>')

    step = 60 if dur > 180 else (30 if dur > 60 else 15)
    ticks, t = [], 0
    while t <= dur + 0.1:
        x = X(t)
        ticks.append(f'<line x1="{x:.1f}" y1="{TRACK_Y + TRACK_H}" x2="{x:.1f}" y2="{TRACK_Y + TRACK_H + 5}" '
                     f'stroke="{MUTE}" stroke-width="1"/>')
        ticks.append(f'<text x="{x:.1f}" y="{TRACK_Y + TRACK_H + 18}" text-anchor="middle" '
                     f'font-size="11" fill="{MUTE}">{fmt(t)}</text>')
        t += step

    scored = [w["score"] for w in words if w.get("score") is not None]
    avg = sum(scored) / len(scored) if scored else None
    low = sum(1 for s in scored if s < 0.5)
    coverage = len(scored) / len(words) * 100 if words else 0
    if (avg is None or avg >= 0.7) and low <= 2 and biggest < 3:
        verdict, vc = "looks good", HI
    elif low > 6 or biggest > 7:
        verdict, vc = "needs a look", LO
    else:
        verdict, vc = "check flags", MID

    name = esc(os.path.basename(a.transcript).replace(".transcript.json", ""))
    avgs = ("%.2f" % avg) if avg is not None else "n/a"
    stat = (f"{len(words)} words · avg conf {avgs} · {low} low-confidence · "
            f"biggest gap {biggest:.1f}s · coverage {coverage:.0f}%")

    lx = PAD
    legend = "".join([
        f'<rect x="{lx}" y="{H-26}" width="11" height="11" rx="2" fill="{HI}"/><text x="{lx+16}" y="{H-16}" font-size="11" fill="{MUTE}">solid</text>',
        f'<rect x="{lx+66}" y="{H-26}" width="11" height="11" rx="2" fill="{MID}"/><text x="{lx+82}" y="{H-16}" font-size="11" fill="{MUTE}">check</text>',
        f'<rect x="{lx+144}" y="{H-26}" width="11" height="11" rx="2" fill="{LO}"/><text x="{lx+160}" y="{H-16}" font-size="11" fill="{MUTE}">likely wrong</text>',
        f'<text x="{lx+254}" y="{H-16}" font-size="11" fill="{MUTE}">blank = gap (no caption)</text>',
    ])

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>'
        f'<text x="{PAD}" y="30" font-size="16" font-weight="600" fill="{INK}">caption footprint — {name}</text>'
        f'<text x="{PAD}" y="50" font-size="12" fill="{MUTE}">{fmt(dur)} · {stat}</text>'
        f'<rect x="{W-PAD-150}" y="16" width="150" height="26" rx="13" fill="{vc}"/>'
        f'<text x="{W-PAD-75}" y="33" text-anchor="middle" font-size="13" font-weight="600" fill="#ffffff">{verdict}</text>'
        f'<rect x="{PAD}" y="{TRACK_Y}" width="{W-2*PAD}" height="{TRACK_H}" rx="4" fill="{TRACK}"/>'
        f'{"".join(blocks)}{"".join(gaps)}{"".join(ticks)}{legend}</svg>'
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[footprint] {verdict} — {stat}")
    print(f"[footprint] -> {out}")


if __name__ == "__main__":
    main()
