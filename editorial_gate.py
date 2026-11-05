from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "script.txt"
OUT = ROOT / "output"
REPORT = OUT / "editorial_gate.txt"
JSON_REPORT = OUT / "editorial_gate.json"

# Remove recurring channel packaging before comparing the actual episode.
BOILERPLATE = [
    r"(?is)^.*?welcome to wise[- ]?lab.*?(?:let's get into\.|let us get into\.)",
    r"(?is)that's it for today from wise[- ]?lab.*$",
    r"(?is)this is wise[- ]?lab\. stay wise.*$",
]
STOP = set("the a an and or but if then than of in on at to for from with by as is are was were be been being it its this that these those you your we our they their he she his her i me my us them what why how when where who which can could would should will just very more most less much many some any not no do does did have has had about into over after before between through during because while also".split())


def episode_text(text: str) -> str:
    value = text.strip()
    for pattern in BOILERPLATE:
        value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
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


def prior_scripts() -> list[tuple[str, str]]:
    try:
        result = subprocess.run(
            ["git", "log", "-n", "21", "--format=%H", "--", "scripts/script.txt"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    commits = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    previous = []
    # Skip HEAD: it is the version currently being evaluated.
    for commit in commits[1:]:
        if len(previous) >= 20:
            break
        try:
            old = subprocess.run(
                ["git", "show", f"{commit}:scripts/script.txt"],
                cwd=ROOT, capture_output=True, text=True, check=True,
            ).stdout
            if old.strip():
                previous.append((commit[:10], old))
        except subprocess.CalledProcessError:
            continue
    return previous


def main() -> int:
    if not SCRIPT.exists():
        raise SystemExit("Missing scripts/script.txt")
    raw = SCRIPT.read_text(encoding="utf-8").strip()
    body = episode_text(raw)
    words = tokens(raw)
    findings: list[str] = []
    blockers: list[str] = []

    if len(words) < 600:
        findings.append(f"Length: {len(words)} words. The long-form target is approximately 900–1,350 words (about 7–10 minutes at 140 WPM).")
    elif len(words) > 1600:
        findings.append(f"Length: {len(words)} words. Check pacing and runtime; this exceeds the usual WISE LAB target.")
    else:
        findings.append(f"Length: {len(words)} words.")

    # Research/statistical language is flagged, never treated as verified.
    claim_patterns = [
        (r"\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b", "Specific percentage or numeric claim"),
        (r"\b(?:study|research|researchers|survey|experiment|meta-analysis|tracked|tracking|found|according to)\b", "Research/evidence claim"),
        (r"\b(?:stanford|harvard|yale|oxford|cambridge|university of|american psychological association|apa)\b", "Named institution or organization"),
        (r"\b(?:202[0-9]|19[89][0-9]|200[0-9]|201[0-9])\b", "Specific year/date"),
        (r"[\u201c\u201d\"]", "Quotation marks: verify exact wording and attribution"),
        (r"\b(?:proves?|guarantees?|always|never|everyone|no one|number one predictor|unbreakable|90 percent of people)\b", "Absolute, causal, or sweeping claim"),
    ]
    for pattern, label in claim_patterns:
        count = len(re.findall(pattern, raw, flags=re.IGNORECASE))
        if count:
            findings.append(f"Evidence review required: {label} ({count} occurrence(s)). Add a traceable primary/authoritative source and check that the wording matches it.")

    if len(re.findall(r"\?", raw)) < 2:
        findings.append("Engagement: few audience-facing questions detected; consider one meaningful reflection question.")
    if len(set(w for w in words if w not in STOP)) < 90:
        findings.append("Originality: low vocabulary variety; check whether the episode develops enough distinct ideas.")

    comparisons = []
    for commit, old in prior_scripts():
        score = similarity(raw, old)
        comparisons.append((score, commit))
    comparisons.sort(reverse=True)
    if comparisons:
        score, commit = comparisons[0]
        findings.append(f"Similarity check: highest overlap with prior episode {commit} is {score:.0%} (recurring intro/outro removed).")
        if score >= 0.84:
            blockers.append(f"Near-duplicate risk: {score:.0%} overlap with prior episode {commit}. Rewrite the main body before rendering.")
    else:
        findings.append("Similarity check: no prior script versions were available for comparison.")

    findings += [
        "Originality check: automated text comparison only; it cannot judge insight, usefulness, or whether visuals add meaning.",
        "Evidence check: automated flags only; this tool does NOT browse sources or fact-check claims.",
        "Before making public: verify every statistic, study, quote, named expert and causal statement against the original source.",
        "Before making public: ensure the episode has a distinct central question, original explanation, concrete everyday examples, practical takeaways and a conclusion—not just a list of generic tips.",
        "Before making public: review the finished video, narration, captions, visual relevance, music licence and thumbnail. Private upload is a review copy, not approval to publish.",
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    status = "HOLD — REWRITE REQUIRED" if blockers else "REVIEW REQUIRED — NOT A FACT-CHECK"
    report = ["WISE LAB — PRE-RENDER EDITORIAL GATE", "", f"Status: {status}", ""] + [f"- {item}" for item in blockers + findings]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    JSON_REPORT.write_text(json.dumps({
        "status": status,
        "word_count": len(words),
        "blockers": blockers,
        "findings": findings,
        "highest_prior_similarity": comparisons[0][0] if comparisons else None,
        "compared_prior_versions": len(comparisons),
        "is_fact_check": False,
    }, indent=2) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 2 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
