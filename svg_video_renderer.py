from __future__ import annotations

"""Render the procedural WISE-LAB SVG scenes as an animated MP4 with original SFX."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from svg_animation_engine import plan_visual_beats, render_scene_svg
from svg_audio_engine import build_sound_events, write_audio_tracks

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

    total_duration = global_frame / fps
    sfx_path = output_dir / "sound_effects.wav"
    mix_path = output_dir / "audio_mix.wav"
    music_seed = int(hashlib.sha256(script.encode('utf-8')).hexdigest()[:8], 16)
    audio_report = write_audio_tracks(total_duration, events, sfx_path, mix_path, music_seed)
    final_video = output_dir / "wise_lab_animated_preview.mp4"
    subprocess.run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent_video), "-i", str(mix_path),
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
        "audio": {**audio_report, "effects_track": sfx_path.name, "mixed_track": mix_path.name,
                  "narration_included": False},
        "stock_media_used": False,
        "external_image_apis_used": False,
        "beats": beats,
        "files": {
            "video": final_video.name,
            "sound_effects": sfx_path.name,
            "audio_mix": mix_path.name,
            "scene_svgs": str(scene_dir.name),
        },
        "sha256": hashlib.sha256(final_video.read_bytes()).hexdigest(),
    }
    (output_dir / "animation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    silent_video.unlink(missing_ok=True)
    print(f"ANIMATED VIDEO READY: {final_video}")
    print(f"SOUND EFFECTS READY: {sfx_path}")
    print(f"MASTERED AUDIO MIX READY: {mix_path}")
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
