#!/usr/bin/env python3
"""
Frame-accurate word timings via forced alignment. Two engines:

  DEFAULT (backward-compatible): whisperX forced alignment (great for single-language speech).
    .venv-whisperx/bin/python scripts/align.py <audio> [--lang en] [--model small] [--out work/transcript.json]

  UNIVERSAL (--code-switch): cs_transcribe (per-segment langID, large-v3) for the WORDS, then
    MMS_FA forced alignment for the TIMING, then validate_timing. Handles ANY language and
    mixed-language (Hinglish/Punjabi-English) audio. Words from ASR, timing from the waveform.
    .venv-whisperx/bin/python scripts/align.py <audio> --code-switch [--dual hi en] [--initial-prompt "..."]

Outputs a flat word list [{text,start,end}, ...] with ABSOLUTE times (matches mountCaptions).
Per the core principle, final timing is ALWAYS forced alignment — never raw ASR timestamps.
"""
import sys, json, argparse, os

SDIR = os.path.dirname(os.path.abspath(__file__))

# languages with a reliable whisperX wav2vec2 alignment model. pa has none and ur's is
# unreliable -> both (and anything else here) go through small + MMS_FA instead
# (matches caption.py's proven pa/ur -> MMS rule).
WX_ALIGN = {"en", "fr", "de", "es", "it", "ja", "zh", "nl", "uk", "pt", "ar", "cs", "ru",
            "pl", "hu", "fi", "fa", "el", "tr", "da", "he", "vi", "ko", "te", "hi", "ca",
            "ml", "no", "nn", "sk", "sl", "hr", "ro", "eu", "gl", "ka", "lv", "tl"}


def whisperx_path(a):
    import whisperx
    device = "cpu"; compute = "int8"
    print(f"[align] whisperX '{a.model}' (faster-whisper)...", file=sys.stderr)
    # --initial-prompt biases the ASR toward supplied names/brands/slang (the glossary),
    # so proper nouns stop being mis-heard. Older whisperx lacks asr_options -> fall back.
    asr_options = {"initial_prompt": a.initial_prompt} if a.initial_prompt else None
    try:
        model = whisperx.load_model(a.model, device, compute_type=compute, language=a.lang,
                                    asr_options=asr_options)
    except TypeError:
        model = whisperx.load_model(a.model, device, compute_type=compute, language=a.lang)
    audio = whisperx.load_audio(a.input)
    result = model.transcribe(audio, language=a.lang, batch_size=8)
    print("[align] forcing alignment...", file=sys.stderr)
    amodel, meta = whisperx.load_align_model(language_code=a.lang, device=device)
    aligned = whisperx.align(result["segments"], amodel, meta, audio, device, return_char_alignments=False)
    words = []
    for w in aligned.get("word_segments", []):
        if "start" in w and "end" in w:
            words.append({"text": w["word"].strip(),
                          "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3),
                          "score": round(float(w.get("score", 0.0) or 0.0), 3)})
    return words


def universal_path(a):
    """cs_transcribe (words) -> MMS_FA (timing, refine off for speech) -> validate."""
    sys.path.insert(0, SDIR)
    import cs_transcribe, mms_align, validate_timing
    cs_words, seg_report = cs_transcribe.transcribe(
        a.input, model_name=a.model_cs, dual=a.dual, initial_prompt=a.initial_prompt)
    langs = sorted(set(r["lang"] for r in seg_report))
    print(f"[align] code-switch: {len(cs_words)} words, per-segment langs={langs}", file=sys.stderr)
    for r in seg_report:
        print(f"    {r['start']}-{r['end']}s  lang={r['lang']}  words={r['words']}", file=sys.stderr)
    display = [w["w"] for w in cs_words]
    timed = mms_align.force_align(a.input, display, lang="auto", window=None, refine=False)
    tagged = [{"text": t["text"], "start": t["start"], "end": t["end"], "score": t["score"]} for t in timed]
    cleaned, warns = validate_timing.validate(tagged, input_count=len(display))
    if warns:
        print(f"[align] validation: {len(warns)} warning(s)", file=sys.stderr)
    return [{"text": c["text"], "start": c.get("start"), "end": c.get("end"), "score": c.get("score")} for c in cleaned]


def single_path(a):
    """One language, FAST: whisperX (small) where it has an aligner, else small + MMS_FA.
    This is the cheap default for normal single-language speech (no large-v3)."""
    lang = a.lang or "en"
    if lang in WX_ALIGN:
        return whisperx_path(a)
    sys.path.insert(0, SDIR)
    import cs_transcribe, mms_align, validate_timing
    print(f"[align] single small+MMS_FA for '{lang}' (no whisperX aligner)...", file=sys.stderr)
    cs_words, _ = cs_transcribe.transcribe(a.input, model_name=a.model, force_lang=lang,
                                           initial_prompt=a.initial_prompt)
    display = [w["w"] for w in cs_words]
    if not display:
        return []
    timed = mms_align.force_align(a.input, display, lang=lang, window=None, refine=False)
    tagged = [{"text": t["text"], "start": t["start"], "end": t["end"], "score": t["score"]} for t in timed]
    cleaned, warns = validate_timing.validate(tagged, input_count=len(display))
    if warns:
        print(f"[align] validation: {len(warns)} warning(s)", file=sys.stderr)
    return [{"text": c["text"], "start": c.get("start"), "end": c.get("end"), "score": c.get("score")} for c in cleaned]


def script_path(a):
    """User supplied the EXACT correct words (--script): skip ASR entirely and only
    force-align them onto the waveform. Content accuracy is 100% (the words are given);
    we compute nothing but their timing. Best for songs/scripts where the text exists."""
    sys.path.insert(0, SDIR)
    import mms_align, validate_timing
    raw = open(a.script, encoding="utf-8").read() if os.path.exists(a.script) else a.script
    display = raw.split()
    if not display:
        print("[align] --script was empty.", file=sys.stderr)
        return []
    print(f"[align] supplied script: {len(display)} words -> timing only, no ASR "
          f"(100% content accuracy)", file=sys.stderr)
    timed = mms_align.force_align(a.input, display, lang=(a.lang or "auto"), window=None, refine=False)
    tagged = [{"text": t["text"], "start": t["start"], "end": t["end"], "score": t["score"]} for t in timed]
    cleaned, warns = validate_timing.validate(tagged, input_count=len(display))
    if warns:
        print(f"[align] validation: {len(warns)} warning(s)", file=sys.stderr)
    return [{"text": c["text"], "start": c.get("start"), "end": c.get("end"), "score": c.get("score")} for c in cleaned]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--model", default="small", help="whisperX/small model for the SINGLE path")
    ap.add_argument("--out", default="work/transcript.json")
    ap.add_argument("--lang-mode", dest="lang_mode", choices=["auto", "single", "code-switch"],
                    default="auto", help="auto = router (default); single = force small; "
                                         "code-switch = force large-v3")
    ap.add_argument("--code-switch", action="store_true", help="legacy alias for --lang-mode code-switch")
    ap.add_argument("--model-cs", dest="model_cs", default="large-v3",
                    help="faster-whisper model for code-switch transcription")
    ap.add_argument("--dual", nargs=2, default=None, metavar=("LANG_A", "LANG_B"))
    ap.add_argument("--initial-prompt", dest="initial_prompt", default=None,
                    help="bias ASR toward these names/brands/slang (the glossary) so they aren't mis-heard")
    ap.add_argument("--script", default=None,
                    help="path to (or literal text of) the EXACT correct words/lyrics; skips ASR and only "
                         "times them -> 100%% content accuracy when you already have the text")
    # router knobs
    ap.add_argument("--cs-scan-model", dest="cs_scan_model", default="small")
    ap.add_argument("--cs-min-seg-share", dest="cs_min_seg_share", type=float, default=0.20)
    ap.add_argument("--cs-min-lang-prob", dest="cs_min_lang_prob", type=float, default=0.55)
    ap.add_argument("--cs-min-lang-seconds", dest="cs_min_lang_seconds", type=float, default=4.0)
    ap.add_argument("--cs-detect-only", dest="cs_detect_only", action="store_true",
                    help="run only the langID scan, print the routing plan, exit")
    a = ap.parse_args()

    if a.code_switch:           # backward-compat
        a.lang_mode = "code-switch"

    def _plan():
        sys.path.insert(0, SDIR)
        import lang_router
        return lang_router.detect_language_plan(
            a.input, a.cs_scan_model, a.cs_min_seg_share, a.cs_min_lang_prob, a.cs_min_lang_seconds)

    if a.cs_detect_only:
        print(json.dumps(_plan(), ensure_ascii=False, indent=2))
        return

    if a.script:                # known-correct words supplied -> time them, skip ASR entirely
        words = script_path(a)
    else:
        mode = a.lang_mode
        if mode == "auto":
            plan = _plan()
            sys.stderr.write(f"[align] router -> {plan['mode']} | {plan['reason']} | "
                             f"scan {plan['scan_seconds']}s\n")
            mode = plan["mode"]
            if mode == "single" and plan.get("primary"):
                a.lang = plan["primary"]

        if mode == "code-switch":
            words = universal_path(a)
        else:
            words = single_path(a)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(words, open(a.out, "w"), ensure_ascii=False, indent=2)
    print(f"[align] {len(words)} words (forced-aligned) -> {a.out}")
    for w in words[:10]:
        s = w.get("start"); e = w.get("end")
        print(f"  {s if s is None else round(s,2):>6}-{e if e is None else round(e,2):<6}  {w['text']}")


if __name__ == "__main__":
    main()
