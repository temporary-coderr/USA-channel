from __future__ import annotations

"""Render the procedural WISE-LAB SVG scenes as an animated MP4 with original SFX."""

import argparse
from array import array
import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from svg_animation_engine import plan_visual_beats, render_scene_svg

SAMPLE_RATE = 24000
SFX_FOR_ACTION = {
    "thinking": "soft_tick",
    "looking": "ui_click",
    "talking": "ui_click",
    "choosing": "ui_click",
    "walking": "soft_step",
    "turn_away": "soft_whoosh",
    "surprised": "soft_impact",
    "explaining": "soft_tick",
}

def build_sound_events(beats: list[dict], transition_seconds: float = 0.22) -> list[dict]:
    events = [{"time": 0.08, "kind": "logo", "gain": 0.42}]
    cursor = 0.0
    for index, beat in enumerate(beats):
        if index:
            cursor += transition_seconds
            events.append({"time": cursor, "kind": "soft_whoosh", "gain": 0.19})
        kind = SFX_FOR_ACTION.get(beat.get("action"), "soft_tick")
        # Leave breathing room: effects punctuate meaningful beats, not every word.
        if index % 2 == 0 or beat.get("action") in {"surprised", "choosing", "walking"}:
            events.append({"time": cursor + min(0.16, beat["duration_seconds"] * 0.18),
                           "kind": kind, "gain": 0.24 if kind != "soft_impact" else 0.30})
        cursor += float(beat["duration_seconds"])
    return events

def _sound_sample(kind: str, t: float, duration: float, seed: int) -> float:
    p = max(0.0, min(1.0, t / max(duration, 1e-6)))
    if kind == "ui_click":
        return math.sin(2 * math.pi * (1250 - 420*p) * t) * math.exp(-24*p)
    if kind == "soft_tick":
        return (math.sin(2 * math.pi * 740 * t) + 0.35 * math.sin(2 * math.pi * 1480 * t)) * math.exp(-18*p)
    if kind == "soft_step":
        return (math.sin(2 * math.pi * (105 - 38*p) * t) * math.exp(-11*p)
                + 0.12 * math.sin(2 * math.pi * 680 * t) * math.exp(-32*p))
    if kind == "soft_impact":
        return (math.sin(2 * math.pi * (95 - 55*p) * t) * math.exp(-7*p)
                + 0.18 * math.sin(2 * math.pi * 210 * t) * math.exp(-13*p))
    if kind == "soft_whoosh":
        carrier = math.sin(2 * math.pi * (180 + 620*p) * t)
        envelope = math.sin(math.pi * p) ** 1.4
        shimmer = math.sin(2 * math.pi * (310 + seed % 190) * t) * 0.12
        return (carrier + shimmer) * envelope
    if kind == "logo":
        envelope = max(0.0, 1.0-p) ** 1.5
        return (math.sin(2*math.pi*392*t) + 0.45*math.sin(2*math.pi*587.33*t)
                + 0.2*math.sin(2*math.pi*784*t)) * envelope
    return 0.0

def write_sfx_track(duration: float, events: list[dict], output_path: Path) -> None:
    """Synthesize a low-volume mono SFX bed using only Python's standard library."""
    total_frames = max(1, int(math.ceil(duration * SAMPLE_RATE)))
    mixed = array('h', [0]) * total_frames
    durations = {
        "ui_click": 0.075, "soft_tick": 0.105, "soft_step": 0.15,
        "soft_impact": 0.24, "soft_whoosh": 0.34, "logo": 0.72,
    }
    for event_index, event in enumerate(events):
        kind = event["kind"]
        start = max(0, int(float(event["time"]) * SAMPLE_RATE))
        length = int(durations.get(kind, 0.12) * SAMPLE_RATE)
        gain = float(event.get("gain", 0.2))
        for offset in range(min(length, total_frames-start)):
            t = offset / SAMPLE_RATE
            value = _sound_sample(kind, t, length / SAMPLE_RATE, event_index * 97)
            sample = int(max(-1.0, min(1.0, value * gain)) * 32767)
            pos = start + offset
            mixed[pos] = max(-32768, min(32767, mixed[pos] + sample))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        # Stream in blocks to avoid a second full-size PCM copy.
        block = 48000
        for start in range(0, total_frames, block):
            chunk = mixed[start:start+block]
            wav.writeframesraw(chunk.tobytes())
        wav.writeframes(b"")

def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required to encode the animated preview.")
    return path

def render_animated_video(script_path: Path, output_dir: Path, video_format: str = "landscape",
                          target_wpm: int = 140, target_seconds: float = 3.0,
                          fps: int = 12, width: int | None = None) -> dict:
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Install CairoSVG and Pillow before rendering: pip install CairoSVG Pillow") from exc

    script = script_path.read_text(encoding="utf-8").strip()
    vertical = video_format.lower() == "shorts"
    if width is None:
        width = 720
    height = round(width * (16/9 if vertical else 9/16))
    beats = plan_visual_beats(script, target_wpm, target_seconds)
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = output_dir / "scene_svgs"
    scene_dir.mkdir(exist_ok=True)
    transition_frames = max(2, round(fps * 0.22))
    transition_seconds = transition_frames / fps
    events = build_sound_events(beats, transition_seconds)
    cursor = 0.0
    total_duration = (sum(float(b["duration_seconds"]) for b in beats)
                      + max(0, len(beats)-1) * transition_seconds)
    frame_count = max(1, round(total_duration * fps))
    previous_frame = None

    with tempfile.TemporaryDirectory(prefix="wise_lab_frames_") as temp_name:
        frames_dir = Path(temp_name)
        global_frame = 0
        for beat_index, beat in enumerate(beats, 1):
            beat_svg_path = scene_dir / f"{beat['id']}.svg"
            beat_svg_path.write_text(
                render_scene_svg(beat["narration"], beat_index, width, height, phase=0.0),
                encoding="utf-8"
            )
            frame_total = max(4, round(float(beat["duration_seconds"]) * fps))
            first_frame = None
            last_frame = None
            for local_index in range(frame_total):
                phase = local_index / max(1, frame_total - 1)
                svg = render_scene_svg(beat["narration"], beat_index, width, height, phase=phase)
                png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                                             output_width=width, output_height=height)
                image = Image.open(__import__("io").BytesIO(png_bytes)).convert("RGB")
                if first_frame is None:
                    first_frame = image.copy()
                if beat_index > 1 and local_index < transition_frames and previous_frame is not None:
                    alpha = (local_index + 1) / transition_frames
                    image = Image.blend(previous_frame, image, alpha)
                frame_path = frames_dir / f"frame_{global_frame:07d}.png"
                image.save(frame_path, format="PNG", optimize=False)
                global_frame += 1
                last_frame = image.copy()
            previous_frame = last_frame
            cursor += float(beat["duration_seconds"])
            print(f"Rendered animated beat {beat_index}/{len(beats)}: {beat['subject']} / {beat['action']}")

        silent_video = output_dir / "animated_visuals_silent.mp4"
        subprocess.run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-i", str(frames_dir / "frame_%07d.png"),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent_video)
        ], check=True)

    sfx_path = output_dir / "sound_effects.wav"
    write_sfx_track(total_duration, events, sfx_path)
    final_video = output_dir / "wise_lab_animated_preview.mp4"
    subprocess.run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent_video), "-i", str(sfx_path),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        "-movflags", "+faststart", str(final_video)
    ], check=True)

    manifest = {
        "engine": "WISE-LAB Animated SVG Video Renderer",
        "version": 2,
        "source_script": str(script_path),
        "format": video_format,
        "dimensions": [width, height],
        "fps": fps,
        "duration_seconds": round(total_duration, 3),
        "beat_count": len(beats),
        "rendered_frame_count": global_frame,
        "character_animation": ["breathing_bob", "gesture_swing"],
        "camera_animation": ["slow_push_in", "alternating_pan", "background_parallax"],
        "transitions": {"type": "crossfade", "duration_seconds": round(transition_frames/fps, 3)},
        "sound_effects": {"track": sfx_path.name, "event_count": len(events),
                          "types": sorted({event["kind"] for event in events})},
        "stock_media_used": False,
        "external_image_apis_used": False,
        "beats": beats,
        "files": {
            "video": final_video.name,
            "sound_effects": sfx_path.name,
            "scene_svgs": str(scene_dir.name),
        },
        "sha256": hashlib.sha256(final_video.read_bytes()).hexdigest(),
    }
    (output_dir / "animation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    silent_video.unlink(missing_ok=True)
    print(f"ANIMATED VIDEO READY: {final_video}")
    print(f"SOUND EFFECTS READY: {sfx_path}")
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser(description="Render animated WISE-LAB SVG visuals and original sound effects.")
    parser.add_argument("--script", default="scripts/script.txt")
    parser.add_argument("--output", default="output/svg_animation_preview")
    parser.add_argument("--format", choices=("landscape", "shorts"), default="landscape")
    parser.add_argument("--wpm", type=int, default=140)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--width", type=int, default=720, help="Preview width; 720 is suitable for first review.")
    args = parser.parse_args()
    if args.fps < 8 or args.fps > 30:
        parser.error("--fps must be between 8 and 30")
    manifest = render_animated_video(Path(args.script), Path(args.output), args.format,
                                     args.wpm, args.seconds, args.fps, args.width)
    print(f"Rendered {manifest['beat_count']} beats / {manifest['rendered_frame_count']} frames.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
