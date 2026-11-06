from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
VERTICAL = os.getenv("VIDEO_FORMAT", "landscape").lower() == "shorts"
VIDEO = OUT / ("wise_lab_shorts.mp4" if VERTICAL else "wise_lab_video.mp4")
EXPECTED = (1080, 1920) if VERTICAL else (1920, 1080)


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,duration,bit_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict = {"format": "shorts" if VERTICAL else "landscape", "expected_resolution": f"{EXPECTED[0]}x{EXPECTED[1]}"}

    required_files = [
        VIDEO, OUT / "captions.srt", OUT / "captions.ass", OUT / "title.txt",
        OUT / "description.txt", OUT / "voiceover_script.txt",
        OUT / "wise_lab_voiceover.mp3", OUT / "visual_manifest.json",
        OUT / "scene_plan.json", OUT / "editorial_review.txt",
        OUT / "editorial_gate.txt", OUT / "background_music_credit.txt",
        OUT / "wise_lab_thumbnail.jpg",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.is_file() or path.stat().st_size == 0]
    if missing:
        errors.append("Missing or empty deliverables: " + ", ".join(missing))

    if VIDEO.is_file() and VIDEO.stat().st_size:
        try:
            data = probe(VIDEO)
            streams = data.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
            duration = float((data.get("format") or {}).get("duration") or 0)
            size = int((data.get("format") or {}).get("size") or VIDEO.stat().st_size)
            metrics.update({"duration_seconds": round(duration, 2), "size_bytes": size,
                            "video_codec": video_stream.get("codec_name") if video_stream else None,
                            "audio_codec": audio_stream.get("codec_name") if audio_stream else None})
            if not video_stream:
                errors.append("Final MP4 has no video stream.")
            else:
                width, height = int(video_stream.get("width") or 0), int(video_stream.get("height") or 0)
                metrics["resolution"] = f"{width}x{height}"
                if (width, height) != EXPECTED:
                    errors.append(f"Wrong video dimensions: {width}x{height}; expected {EXPECTED[0]}x{EXPECTED[1]}.")
                rate = str(video_stream.get("r_frame_rate") or "0/1")
                try:
                    numerator, denominator = rate.split("/", 1)
                    fps = float(numerator) / max(1.0, float(denominator))
                except (ValueError, ZeroDivisionError):
                    fps = 0.0
                metrics["fps"] = round(fps, 3)
                if not 29.0 <= fps <= 31.0:
                    errors.append(f"Unexpected frame rate: {fps:.3f} fps; expected approximately 30 fps.")
            if not audio_stream:
                errors.append("Final MP4 has no audio stream.")
            else:
                metrics["audio_codec"] = audio_stream.get("codec_name")
                if audio_stream.get("codec_name") not in {"aac", "mp3"}:
                    warnings.append("Audio codec is not the expected AAC/MP3 family; listen to the file before review.")
            if duration <= 0 or size < 100_000:
                errors.append("Final MP4 duration or file size is implausibly small.")
            if not VERTICAL and duration < 240:
                warnings.append("Long-form video is under 4 minutes; check whether the script/render is complete.")
            if VERTICAL:
                if duration > 180:
                    errors.append("Shorts render exceeds YouTube's 3-minute limit.")
                if duration < 30:
                    warnings.append("Short is under the preferred 30-second starting target; check whether the idea feels complete.")
                elif duration > 60:
                    warnings.append("Short is over the preferred 60-second starting target; tighten only if doing so preserves the explanation.")
        except Exception as exc:
            errors.append("ffprobe could not validate the final MP4: " + str(exc))

    script_file = OUT / "voiceover_script.txt"
    plan_file = OUT / "scene_plan.json"
    if script_file.is_file() and plan_file.is_file():
        try:
            script_words = tokens(script_file.read_text(encoding="utf-8"))
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            planned_words = tokens(" ".join(str(s.get("narration", "")) for s in plan.get("scenes", [])))
            metrics["script_word_count"] = len(script_words)
            metrics["scene_count"] = len(plan.get("scenes", []))
            metrics["scene_narration_matches_script"] = script_words == planned_words
            if script_words != planned_words:
                errors.append("Scene narration does not exactly preserve the source script word sequence.")
        except Exception as exc:
            errors.append("Could not validate scene-plan narration: " + str(exc))

    manifest_file = OUT / "visual_manifest.json"
    if manifest_file.is_file():
        try:
            assets = json.loads(manifest_file.read_text(encoding="utf-8"))
            hashes = [str(a.get("sha256")) for a in assets if a.get("sha256")]
            perceptual = [h for a in assets for h in (a.get("visual_hashes") or [])]
            metrics["visual_cut_count"] = len(assets)
            metrics["perceptual_fingerprint_count"] = len(perceptual)
            metrics["original_diagram_count"] = sum(1 for a in assets if "wise-lab original diagram" in str(a.get("source", "")).lower())
            metrics["visual_source_counts"] = dict(Counter(str(a.get("source") or "Pixabay") for a in assets))
            metrics["ai_visual_count"] = sum(1 for a in assets if "openai" in str(a.get("source", "")).lower())
            if len(assets) < 5:
                errors.append(f"Only {len(assets)} visual cuts were recorded; expected at least 5.")
            if len(hashes) != len(assets):
                errors.append("At least one visual has no SHA-256 fingerprint.")
            if len(set(hashes)) != len(hashes):
                errors.append("Duplicate visual fingerprints were found within this video.")
            if len(perceptual) < len(assets):
                errors.append("At least one visual is missing perceptual fingerprints; visual reuse checks are incomplete.")
            long_cuts = [a for a in assets if float(a.get("shot_duration_seconds") or 0) > 6.5]
            if long_cuts:
                warnings.append(f"{len(long_cuts)} visual cut(s) exceed 6.5 seconds; check pacing and relevance.")
        except Exception as exc:
            errors.append("Could not validate visual manifest: " + str(exc))

    source_ledger = ROOT / "scripts" / "research_notes.md"
    if not source_ledger.is_file() or not source_ledger.read_text(encoding="utf-8").strip():
        errors.append("Missing episode research ledger: add scripts/research_notes.md before rendering. Human-approved scripts must include a source ledger or an explicit no-empirical-claims statement.")
        metrics["research_ledger_present"] = False
    else:
        ledger_text = source_ledger.read_text(encoding="utf-8").strip()
        metrics["research_ledger_present"] = True
        has_source_url = "http://" in ledger_text or "https://" in ledger_text
        declares_no_claims = bool(re.search(r"(?im)^no specific empirical claims\b", ledger_text))
        if not has_source_url and not declares_no_claims:
            errors.append("Research ledger needs source URLs or an explicit no-specific-empirical-claims statement before rendering.")

    captions = OUT / "captions.srt"
    if captions.is_file():
        caption_text = captions.read_text(encoding="utf-8").strip()
        if "-->" not in caption_text or len(re.findall(r"(?m)^\d+$", caption_text)) < 5:
            errors.append("Caption sidecar is missing or has too few timed entries.")

    status = "FAIL" if errors else ("REVIEW WITH WARNINGS" if warnings else "TECHNICAL CHECKS PASSED — HUMAN REVIEW REQUIRED")
    metrics.update({"status": status, "errors": errors, "warnings": warnings,
                    "automated_checks_are_fact_check": False})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "technical_quality.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    report = ["WISE LAB — TECHNICAL QUALITY REPORT", "", f"Status: {status}", ""]
    report += [f"ERROR: {item}" for item in errors]
    report += [f"WARNING: {item}" for item in warnings]
    report += ["", "Metrics:", json.dumps({k: v for k, v in metrics.items() if k not in {"errors", "warnings"}}, indent=2),
               "", "This check verifies file structure and basic media integrity only. It does not verify facts, licensing, originality, or creative quality."]
    (OUT / "technical_quality.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

    checklist = [
        "# WISE LAB — Human review and approval",
        "",
        f"- Video format: {'Shorts (9:16)' if VERTICAL else 'Long-form (16:9)'}",
        f"- Technical status: **{status}**",
        "",
        "## Review the actual video",
        "- [ ] Watch the full video once; confirm the opening hook earns attention and the ending feels complete.",
        "- [ ] Listen on headphones and phone speakers: Andrew voice is clear, natural, consistent and never covered by music.",
        "- [ ] Check every visual against the exact narration; remove irrelevant, repeated, awkward or misleading shots.",
        "- [ ] Check captions for spelling, timing, readability, safe margins and correct names.",
        "- [ ] Check transitions, pacing, no unintended black/frozen frames, and no abrupt audio cuts.",
        *([
            "- [ ] Confirm the opening works immediately without an intro and the first frame communicates the topic.",
            "- [ ] Confirm vertical captions and key visuals stay clear of top/bottom app interface safe areas.",
            "- [ ] Check for purposeful visual changes roughly every 1–3 seconds where appropriate; do not sacrifice clarity for speed.",
            "- [ ] Confirm this is a Short-specific story/edit, not merely a landscape video cropped to 9:16.",
            "- [ ] Confirm there is no long-form intro/outro and the final thought is complete."
        ] if VERTICAL else []),
        "- [ ] Check thumbnail, title and description accurately represent the episode; no exaggerated promise or misleading claim.",
        "",
        "## Evidence and rights",
        "- [ ] Verify each statistic, study, quote, named institution and causal claim against the original source.",
        "- [ ] Confirm sources support the exact wording and population; remove claims that cannot be verified.",
        "- [ ] Open the visual manifest and description; verify asset credits and each licence/usage condition.",
        "- [ ] Confirm the background music track and licence/attribution are suitable for the intended use.",
        "- [ ] Confirm the episode adds original explanation, examples and practical value—not just generic tips or stock footage.",
        "",
        "## Final decision",
        "- [ ] APPROVE: publish manually in YouTube Studio only after every required check passes.",
        "- [ ] HOLD: keep the YouTube upload private and record the corrections needed.",
        "",
        "**Important:** a successful technical check is not a fact-check or a YouTube monetization guarantee. This workflow uploads privately for review and never makes a video public automatically.",
        "",
        "Files to inspect: title.txt, description.txt, voiceover_script.txt, scripts/research_notes.md, editorial_gate.txt, editorial_review.txt, technical_quality.txt, visual_manifest.json, background_music_credit.txt.",
    ]
    (OUT / "review_checklist.md").write_text("\n".join(checklist) + "\n", encoding="utf-8")
    print("\n".join(report))
    if errors:
        return 2
    print("\nHuman review checklist created: output/review_checklist.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
