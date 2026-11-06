from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "script.txt"
OUT = ROOT / "output"
REPORT = OUT / "editorial_gate.txt"
JSON_REPORT = OUT / "editorial_gate.json"
HISTORY = ROOT / "editorial_history" / "rendered_scripts.json"

STOP = set("the a an and or but if then than of in on at to for from with by as is are was were be been being it its this that these those you your we our they their he she his her i me my us them what why how when where who which can could would should will just very more most less much many some any not no do does did have has had about into over after before between through during because while also".split())


def episode_text(text: str) -> str:
    # Strip recurring channel branding so it does not inflate overlap.
    value = re.sub(r"(?is)\bwelcome to wise[- ]?lab\b", " ", text)
    value = re.sub(r"(?is)\bfollow wise[- ]?lab\b.*$", " ", value)
    value = re.sub(r"(?is)\bfollow for more psychology\b.*$", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", episode_text(text))


def shingles(words: list[str], size: int = 5) -> set[tuple[str, ...]]:
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def similarity(a: str, b: str) -> float:
    wa, wb = tokens(a), tokens(b)
    if not wa or not wb:
        return 0.0
    seq = difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio()
    sa, sb = shingles(wa), shingles(wb)
    jac = len(sa & sb) / max(1, len(sa | sb))
    return max(seq, jac)


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def current_script() -> tuple[str, str, list[str], str]:
    if not SCRIPT.exists():
        raise SystemExit("Missing scripts/script.txt")
    raw = SCRIPT.read_text(encoding="utf-8").strip()
    body = episode_text(raw)
    words = tokens(raw)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return raw, body, words, digest


def record_rendered() -> int:
    raw, body, words, digest = current_script()
    expected = "wise_lab_shorts.mp4" if os.getenv("VIDEO_FORMAT", "landscape").lower() == "shorts" else "wise_lab_video.mp4"
    rendered_file = OUT / expected
    if not rendered_file.exists() or rendered_file.stat().st_size == 0:
        raise SystemExit(f"Refusing to record script: rendered video not found at {rendered_file}")
    history = load_history()
    if not any(item.get("sha256") == digest for item in history):
        history.append({
            "sha256": digest,
            "script": body,
            "word_count": len(words),
            "format": os.getenv("VIDEO_FORMAT", "landscape").lower(),
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Recorded successfully rendered script ({len(words)} words) in {HISTORY.relative_to(ROOT)}.")
    else:
        print("This exact script is already in the successfully-rendered history.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-rendered", action="store_true", help="Record this script only after its MP4 exists.")
    args = parser.parse_args()
    if args.record_rendered:
        return record_rendered()

    raw, body, words, digest = current_script()
    video_format = os.getenv("VIDEO_FORMAT", "landscape").strip().lower()
    if video_format not in {"shorts", "landscape"}:
        video_format = "landscape"

    findings: list[str] = []
    blockers: list[str] = []

    if video_format == "shorts":
        if len(words) < 70:
            findings.append(f"Shorts length: {len(words)} words. Preferred range is approximately 70–140 words; confirm actual narration duration.")
        elif len(words) > 140:
            findings.append(f"Shorts length: {len(words)} words. This is above the preferred 70–140-word range; confirm actual narration duration and pacing.")
        else:
            findings.append(f"Shorts length: {len(words)} words (within the preferred 70–140-word range). Actual narration duration remains authoritative.")
        if len(words) > 180:
            findings.append("Shorts review: script exceeds 180 words; strongly consider tightening it.")
    else:
        if len(words) < 600:
            findings.append(f"Long-form length: {len(words)} words. The usual target is approximately 900–1,350 words (about 7–10 minutes at 140 WPM).")
        elif len(words) > 1600:
            findings.append(f"Long-form length: {len(words)} words. Check pacing and runtime; this exceeds the usual WISE-LAB target.")
        else:
            findings.append(f"Long-form length: {len(words)} words.")

    claim_patterns = [
        (r"\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b", "Specific percentage or numeric claim"),
        (r"\b(?:study|research|researchers|survey|experiment|meta-analysis|tracked|tracking|found|according to)\b", "Research/evidence claim"),
        (r"\b(?:stanford|harvard|yale|oxford|cambridge|cornell|university of|american psychological association|apa)\b", "Named institution or organization"),
        (r"\b(?:202[0-9]|19[89][0-9]|200[0-9]|201[0-9])\b", "Specific year/date"),
        (r"[\u201c\u201d\"]", "Quotation marks: verify exact wording and attribution"),
        (r"\b(?:proves?|guarantees?|always|never|everyone|no one|number one predictor|unbreakable)\b", "Absolute, causal, or sweeping claim"),
    ]
    for pattern, label in claim_patterns:
        count = len(re.findall(pattern, raw, flags=re.IGNORECASE))
        if count:
            findings.append(f"Evidence review required: {label} ({count} occurrence(s)). Add a traceable source and check that the wording matches it.")

    if len(re.findall(r"\?", raw)) < 1:
        findings.append("Engagement: consider adding one meaningful audience-facing question.")
    if len(set(w for w in words if w not in STOP)) < 45:
        findings.append("Originality: low vocabulary variety; check whether the episode develops enough distinct ideas.")

    comparisons = []
    for item in load_history():
        old_script = item.get("script", "")
        if not old_script:
            continue
        score = similarity(raw, old_script)
        comparisons.append((score, item.get("sha256", "unknown"), item.get("recorded_at_utc", "unknown")))
    comparisons.sort(reverse=True, key=lambda item: item[0])
    if comparisons:
        score, old_hash, recorded_at = comparisons[0]
        findings.append(f"Similarity check: highest overlap with a previously rendered episode is {score:.0%} (recorded {recorded_at}).")
        if score >= 0.84:
            blockers.append(f"Near-duplicate risk: {score:.0%} overlap with a previously rendered episode (script hash {old_hash[:12]}). Rewrite the main body before rendering.")
    else:
        findings.append("Similarity check: no successfully rendered prior scripts are recorded yet; this episode will be added to history only after an MP4 is created.")

    findings += [
        "Originality check: automated text comparison only; it cannot judge insight, usefulness, or whether visuals add meaning.",
        "Evidence check: automated flags only; this tool does NOT browse sources or fact-check claims.",
        "Before making public: verify every statistic, study, quote, named expert and causal statement against the original source.",
        "Before making public: ensure the episode has a distinct central question, original explanation, concrete everyday examples, practical takeaways and a conclusion—not just a list of generic tips.",
        "Before making public: review the finished video, narration, captions, visual relevance, music licence and thumbnail. Private upload is a review copy, not approval to publish.",
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    status = "HOLD — REWRITE REQUIRED" if blockers else "REVIEW REQUIRED — NOT A FACT-CHECK"
    report = ["WISE LAB — PRE-RENDER EDITORIAL GATE", "", f"Format: {video_format}", f"Status: {status}", ""] + [f"- {item}" for item in blockers + findings]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    JSON_REPORT.write_text(json.dumps({
        "status": status,
        "format": video_format,
        "word_count": len(words),
        "blockers": blockers,
        "findings": findings,
        "highest_prior_similarity": comparisons[0][0] if comparisons else None,
        "compared_successfully_rendered_scripts": len(comparisons),
        "is_fact_check": False,
        "script_sha256": digest,
    }, indent=2) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
