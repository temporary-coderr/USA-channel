from __future__ import annotations

"""Fail the prototype build if the final MP4 is missing core publication elements."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return result.stdout


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "output/svg_animation_preview")
    video = root / "wise_lab_animated_preview.mp4"
    narration = root / "narration.wav"
    captions = root / "captions.ass"
    manifest_path = root / "animation_manifest.json"
    for required in (video, narration, captions, manifest_path):
        if not required.is_file() or required.stat().st_size == 0:
            raise SystemExit(f"QUALITY GATE FAILED: missing or empty {required.name}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("audio", {}).get("narration_included"):
        raise SystemExit("QUALITY GATE FAILED: manifest says narration is absent")
    if not manifest.get("captions", {}).get("burned_in"):
        raise SystemExit("QUALITY GATE FAILED: captions are not marked burned in")

    caption_text = captions.read_text(encoding="utf-8")
    caption_events = re.findall(r"^Dialogue:\s", caption_text, flags=re.MULTILINE)
    expected_beats = int(manifest.get("beat_count", 0))
    if expected_beats < 1 or len(caption_events) != expected_beats:
        raise SystemExit(
            f"QUALITY GATE FAILED: {len(caption_events)} caption events for {expected_beats} beats"
        )

    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise SystemExit("QUALITY GATE FAILED: ffprobe/ffmpeg unavailable")
    probe = json.loads(run([
        ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)
    ]))
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams or not audio_streams:
        raise SystemExit("QUALITY GATE FAILED: final MP4 must contain video and audio streams")
    v = video_streams[0]
    if int(v.get("width", 0)) != int(manifest["dimensions"][0]) or int(v.get("height", 0)) != int(manifest["dimensions"][1]):
        raise SystemExit("QUALITY GATE FAILED: MP4 dimensions differ from manifest")
    duration = float(probe.get("format", {}).get("duration", 0))
    narration_duration = float(run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(narration)
    ]).strip())
    if duration <= 0 or abs(duration - narration_duration) > 0.35:
        raise SystemExit(
            f"QUALITY GATE FAILED: video ({duration:.2f}s) and narration ({narration_duration:.2f}s) durations differ"
        )

    loudness = run([
        ffmpeg, "-hide_banner", "-i", str(video), "-af", "volumedetect",
        "-vn", "-f", "null", "-"
    ])
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", loudness)
    if not mean_match or mean_match.group(1) == "-inf":
        raise SystemExit("QUALITY GATE FAILED: final audio is silent or could not be measured")

    print(
        "QUALITY GATE PASSED: "
        f"{v['width']}x{v['height']}, {duration:.2f}s, "
        f"{len(caption_events)} caption events, "
        f"audio mean {mean_match.group(1)} dB, "
        f"video codec {v.get('codec_name')}, audio codec {audio_streams[0].get('codec_name')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
