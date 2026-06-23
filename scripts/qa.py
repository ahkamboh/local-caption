#!/usr/bin/env python3
"""
qa.py — fast, deterministic QA gate for a captioned video. No tokens, no human, no pixels.

It verifies the things that can break MECHANICALLY (timing/confidence are already enforced
during alignment by validate_timing.py; word-accuracy of the transcript needs a human/LLM —
see the README). This is the final-output gate: it reads the .srt + ffprobes the input and
output, writes work/<base>.qa.json, and prints a one-line verdict. With --strict, a FAIL
exits non-zero so a pipeline can stop on a broken result.

Checks:
  • captions_present   >=1 cue (ASR didn't return empty)
  • times_in_range     every cue inside [0, video duration]
  • no_zero_length     no zero/negative-length cues
  • no_overlap         cues don't overlap            (warn)
  • density_sane       not e.g. 1 cue for a 5-min video → likely ASR failure  (warn)
  • output_has_video   the burned file has a video stream
  • audio_preserved    audio survived the burn (if the source had any)        (warn)
  • dims_match         output resolution == input resolution

Usage:  python scripts/qa.py INPUT OUTPUT SRT [--strict] [--out work/x.qa.json]
"""
import sys, os, re, json, argparse, subprocess


def _ffprobe(path):
    """Return {w,h,dur,has_audio} for a media file, or None on failure."""
    if not path or not os.path.exists(path):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height:format=duration", "-of", "json", path],
            capture_output=True, text=True).stdout
        d = json.loads(out or "{}")
    except Exception:
        return None
    w = h = None
    has_audio = False
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and w is None:
            w, h = s.get("width"), s.get("height")
        if s.get("codec_type") == "audio":
            has_audio = True
    dur = float(d.get("format", {}).get("duration", 0) or 0)
    return {"w": w, "h": h, "dur": dur, "has_audio": has_audio}


def _ts(t):
    t = t.strip().replace(".", ",")
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    cues = []
    if not path or not os.path.exists(path):
        return cues
    for blk in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().strip()):
        lines = [l for l in blk.splitlines() if l.strip()]
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = tl.split("-->")
        txt = " ".join(lines[lines.index(tl) + 1:]).strip()
        cues.append((_ts(a), _ts(b), txt))
    return cues


def qa(inp, out, srt):
    checks = []

    def add(name, ok, detail, warn=False):
        checks.append({"check": name,
                       "status": ("pass" if ok else ("warn" if warn else "fail")),
                       "detail": detail})

    src = _ffprobe(inp) or {}
    dur = src.get("dur", 0) or 0
    cues = parse_srt(srt)

    add("captions_present", len(cues) > 0, f"{len(cues)} cue(s)")

    bad_range = bad_dur = overlaps = 0
    prev_end = -1.0
    for s, e, _ in cues:
        if s < -0.05 or (dur and e > dur + 0.5):
            bad_range += 1
        if e <= s:
            bad_dur += 1
        if s < prev_end - 0.05:
            overlaps += 1
        prev_end = e
    add("times_in_range", bad_range == 0, f"{bad_range} cue(s) outside [0, {dur:.1f}s]")
    add("no_zero_length", bad_dur == 0, f"{bad_dur} zero/negative-length cue(s)")
    add("no_overlap", overlaps == 0, f"{overlaps} overlapping cue(s)", warn=True)

    if dur > 30 and cues:
        expected = dur / 30.0
        add("density_sane", len(cues) >= expected,
            f"{len(cues)} cues over {dur:.0f}s (≈{expected:.0f} expected)", warn=True)

    o = _ffprobe(out)
    add("output_has_video", bool(o and o.get("w")),
        "video stream present" if (o and o.get("w")) else "no video stream / output missing")
    in_audio, out_audio = bool(src.get("has_audio")), bool(o and o.get("has_audio"))
    add("audio_preserved", (not in_audio) or out_audio,
        "audio preserved" if out_audio else ("source had no audio" if not in_audio else "audio dropped"),
        warn=True)
    dims_ok = bool(o and src and o.get("w") == src.get("w") and o.get("h") == src.get("h"))
    add("dims_match", dims_ok,
        f"{(o or {}).get('w')}x{(o or {}).get('h')} vs {src.get('w')}x{src.get('h')}")

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    status = "fail" if fails else ("warn" if warns else "pass")
    return {"status": status, "checks": checks}, fails, warns


def main():
    ap = argparse.ArgumentParser(description="fast deterministic QA gate for a captioned video")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("srt")
    ap.add_argument("--out", default=None, help="path for the qa.json report")
    ap.add_argument("--strict", action="store_true", help="exit non-zero if any check FAILS")
    a = ap.parse_args()

    report, fails, warns = qa(a.input, a.output, a.srt)
    out = a.out or os.path.join("work", os.path.splitext(os.path.basename(a.input))[0] + ".qa.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(report, open(out, "w"), ensure_ascii=False, indent=2)

    tag = {"pass": "PASS", "warn": "PASS (warnings)", "fail": "FAIL"}[report["status"]]
    print(f"[qa] {tag} — {len(report['checks'])} checks, {len(fails)} fail, {len(warns)} warn -> {out}")
    for c in fails + warns:
        print(f"     {c['status'].upper()}: {c['check']} — {c['detail']}")
    if a.strict and fails:
        sys.exit(2)


if __name__ == "__main__":
    main()
