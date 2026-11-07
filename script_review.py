from __future__ import annotations
"""Free editorial review and YouTube metadata suggestions for WISE-LAB."""

import argparse
import json
import os
import re
from pathlib import Path
import requests

URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"


def fallback_review(script: str) -> dict:
    words = re.findall(r"\b[\w'-]+\b", script)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script) if s.strip()]
    claims = []
    for sentence in sentences:
        if re.search(r"\b(proved|researchers|study|studies|scientists|research|in \d{4}|percent|\d+%|hormone|brain)\b", sentence, re.I):
            claims.append({"claim": sentence, "check": "Add a credible primary or review source before publishing."})
    title = re.sub(r"[^\w\s?'!-]", "", sentences[0] if sentences else "Psychology explained")[:62].strip()
    return {
        "review_mode": "local_fallback",
        "word_count": len(words),
        "hook": "Open with a concrete situation, surprising question, or clear tension.",
        "retention": ["Use a fresh visual or example when the idea changes.", "Pay off the opening promise before the ending."],
        "clarity": ["Explain technical terms in everyday US English.", "Remove repetition and unsupported absolutes."],
        "claims_to_verify": claims,
        "title_options": [title or "The Psychology Behind Everyday Behavior"],
        "description": "A practical psychology explainer. Add an accurate summary and relevant source links before publishing.",
        "tags": ["psychology", "human behavior", "behavior science", "mind", "psychology explained"],
        "thumbnail_concept": "One expressive character, one recognizable object, and a short curiosity-driven phrase.",
        "improvements": ["Check every factual claim against reliable sources.", "Make the opening promise specific.", "Keep the call to action natural."],
        "seo_note": "Use the main topic naturally in the title and first description lines. Metadata does not guarantee rankings."
    }


def review_script(script: str, timeout: int = 40) -> dict:
    fallback = fallback_review(script)
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return fallback
    model = os.getenv("GROQ_STORY_MODEL", MODEL).strip() or MODEL
    prompt = (
        "Act as a rigorous US-audience psychology YouTube editor and metadata strategist. "
        "Review hook truthfulness, retention, plain-English clarity, specificity, originality, "
        "and natural search discoverability. Never keyword-stuff or invent research, sources, "
        "statistics, or certainty. You cannot verify claims from the script alone: list material "
        "science/research claims needing sources. Do not rewrite the script. Return JSON with "
        "hook (string), retention (2-5 strings), clarity (2-5 strings), claims_to_verify "
        "(objects with claim and check), title_options (3 accurate titles max 65 chars), "
        "description (accurate, useful first two lines, no fake sources), tags (8-15 relevant "
        "tags), thumbnail_concept (string), improvements (3-6 concrete edits), seo_note (string). "
        "Script:\n" + script[:12000]
    )
    try:
        response = requests.post(
            URL,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.25,
                "max_completion_tokens": 2200,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Return valid JSON only. Be skeptical and factual."},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=timeout
        )
        response.raise_for_status()
        data = json.loads(response.json()["choices"][0]["message"]["content"])
        required = ["hook", "retention", "clarity", "claims_to_verify", "title_options",
                    "description", "tags", "thumbnail_concept", "improvements", "seo_note"]
        if any(field not in data for field in required):
            raise ValueError("Review response is missing fields")
        if not isinstance(data["claims_to_verify"], list) or not isinstance(data["title_options"], list):
            raise ValueError("Review response has invalid list fields")
        data["review_mode"] = "groq_editorial_review"
        data["model"] = model
        data["word_count"] = len(re.findall(r"\b[\w'-]+\b", script))
        return data
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        fallback["review_mode"] = "local_fallback_after_api_error"
        return fallback


def write_review(script_path: Path, output_dir: Path) -> tuple[Path, Path]:
    source = script_path.read_text(encoding="utf-8").strip()
    if not source:
        raise ValueError("The script is empty.")
    report = review_script(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "content_review.json"
    md_path = output_dir / "content_review.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# WISE-LAB content review", "",
        f"- Word count: {report.get('word_count', 0)}",
        f"- Review mode: {report.get('review_mode', 'unknown')}", "",
        "## Hook", str(report.get("hook", "")), "",
        "## Retention", *["- " + str(x) for x in report.get("retention", [])], "",
        "## Clarity", *["- " + str(x) for x in report.get("clarity", [])], "",
        "## Claims to verify"
    ]
    claims = report.get("claims_to_verify", [])
    if claims:
        lines.extend(["- **" + str(x.get("claim", "")) + "** — " + str(x.get("check", "")) for x in claims])
    else:
        lines.append("- No claims flagged by the automated review; still fact-check the script.")
    lines.extend([
        "", "## Suggested titles", *["- " + str(x) for x in report.get("title_options", [])],
        "", "## Description", str(report.get("description", "")),
        "", "## Tags", ", ".join(report.get("tags", [])),
        "", "## Thumbnail concept", str(report.get("thumbnail_concept", "")),
        "", "## Improvements", *["- " + str(x) for x in report.get("improvements", [])],
        "", "## Search note", str(report.get("seo_note", "")),
        "", "> Editorial assistance only; not independent scientific fact-checking or a ranking guarantee."
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", default="scripts/script.txt")
    parser.add_argument("--output", default="output/content_review")
    args = parser.parse_args()
    json_path, md_path = write_review(Path(args.script), Path(args.output))
    print("Content review ready: " + str(md_path) + " and " + str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
