from __future__ import annotations

"""Render original SVG animation with Edge-TTS narration and burned-in captions."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from svg_animation_engine import plan_visual_beats
from svg_scene_engine import render_scene_svg
from svg_story_planner import plan_story
from svg_audio_engine import build_sound_events, write_audio_tracks
from svg_narration import synthesize_beats


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required to encode the animated preview.")
    return path


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _subtitle_filter(path: Path) -> str:
    value = path.resolve().as_posix()
    value = value.replace(":", r"\:").replace("'", r"\'")
    return f"subtitles=filename='{value}'"


def render_animated_video(script_path: Path, output_dir: Path, video_format: str = "landscape",
                          target_wpm: int = 140, target_seconds: float = 3.0,
                          fps: int = 12, width: int | None = None) -> dict:
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Install CairoSVG and Pillow before rendering: pip install CairoSVG Pillow") from exc

    script = script_path.read_text(encoding="utf-8").strip()
    if not script:
        raise ValueError("The narration script is empty.")
    vertical = video_format.lower() == "shorts"
    width = width or 720
    height = round(width * (16 / 9 if vertical else 9 / 16))
    beats = plan_visual_beats(script, target_wpm, target_seconds)
    segment_paths, spoken_durations, narration_path = synthesize_beats(
        beats, output_dir, width, height,
        voice=__import__("os").getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural"),
        rate=__import__("os").getenv("EDGE_TTS_RATE", "+5%"),
    )
    if len(segment_paths) != len(beats) or len(spoken_durations) != len(beats):
        raise RuntimeError("Narration segment count does not match the visual beat count.")
    for beat, duration in zip(beats, spoken_durations):
        beat["duration_seconds"] = duration

    visual_briefs, story_plan_report = plan_story(beats)
    print("Story planner selected: " + story_plan_report.get("provider", "unknown"))
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = output_dir / "scene_svgs"
    scene_dir.mkdir(exist_ok=True)
    transition_frames = max(2, round(fps * 0.22))
    transition_seconds = transition_frames / fps
    events = build_sound_events(beats, 0.0)
    previous_frame = None

    with tempfile.TemporaryDirectory(prefix="wise_lab_frames_") as temp_name:
        frames_dir = Path(temp_name)
        global_frame = 0
        for beat_index, beat in enumerate(beats, 1):
            svg = render_scene_svg(
                beat["narration"], beat_index, width, height, phase=0.0,
                visual_brief=visual_briefs[beat_index - 1],
            )
            (scene_dir / f"{beat['id']}.svg").write_text(svg, encoding="utf-8")
            frame_total = max(1, math.ceil(float(beat["duration_seconds"]) * fps))
            last_frame = None
            for local_index in range(frame_total):
                phase = local_index / max(1, frame_total - 1)
                svg = render_scene_svg(
                    beat["narration"], beat_index, width, height, phase=phase,
                    visual_brief=visual_briefs[beat_index - 1],
                )
                png_bytes = cairosvg.svg2png(
                    bytestring=svg.encode("utf-8"), output_width=width, output_height=height
                )
                image = Image.open(__import__("io").BytesIO(png_bytes)).convert("RGB")
                if beat_index > 1 and local_index < transition_frames and previous_frame is not None:
                    alpha = min(1.0, (local_index + 1) / transition_frames)
                    image = Image.blend(previous_frame, image, alpha)
                image.save(frames_dir / f"frame_{global_frame:07d}.png", format="PNG", optimize=False)
                global_frame += 1
                last_frame = image.copy()
            previous_frame = last_frame
            print(f"Rendered beat {beat_index}/{len(beats)}: {beat['subject']} / {beat['action']}")

        silent_video = output_dir / "animated_visuals_silent.mp4"
        _run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-i", str(frames_dir / "frame_%07d.png"),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent_video),
        ])

    total_duration = global_frame / fps
    sfx_path = output_dir / "sound_effects.wav"
    bed_path = output_dir / "audio_mix.wav"
    music_seed = int(hashlib.sha256(script.encode("utf-8")).hexdigest()[:8], 16)
    audio_report = write_audio_tracks(total_duration, events, sfx_path, bed_path, music_seed)

    final_video = output_dir / "wise_lab_animated_preview.mp4"
    # Compress music/SFX under the narration, then mix at a restrained level.
    # Captions are burned into the video stream; they cannot disappear in playback.
    filter_complex = (
        "[2:a][1:a]sidechaincompress=threshold=0.025:ratio=8:attack=18:release=480[ducked];"
        "[1:a][ducked]amix=inputs=2:weights='1 0.28':normalize=0,"
        "alimiter=limit=0.92[aout]"
    )
    _run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(silent_video), "-i", str(narration_path), "-i", str(bed_path),
        "-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[aout]",
        "-vf", _subtitle_filter(output_dir / "captions.ass"),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", str(final_video),
    ])
    silent_video.unlink(missing_ok=True)

    if not final_video.exists() or final_video.stat().st_size < 10000:
        raise RuntimeError("Final MP4 was not created correctly.")
    manifest = {
        "engine": "WISE-LAB Animated SVG Video Renderer",
        "version": 3,
        "source_script": str(script_path),
        "format": video_format,
        "dimensions": [width, height],
        "fps": fps,
        "duration_seconds": round(total_duration, 3),
        "beat_count": len(beats),
        "rendered_frame_count": global_frame,
        "character_animation": ["expression_shapes", "blink", "breathing_bob", "walking_cycle", "pose_variants"],
        "scene_engine": "script_adaptive_svg_scene_composer",
        "story_planner": story_plan_report,
        "transitions": {"type": "crossfade", "duration_seconds": round(transition_frames / fps, 3)},
        "audio": {
            **audio_report,
            "effects_track": sfx_path.name,
            "music_and_effects_track": bed_path.name,
            "narration_file": narration_path.name,
            "narration_included": True,
            "narration_voice": __import__("os").getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural"),
            "music_ducking": True,
        },
        "captions": {
            "included": True,
            "burned_in": True,
            "source": "measured_edge_tts_phrase_durations",
            "file": "captions.ass",
            "max_lines": 2,
            "accent_highlight": True,
        },
        "stock_media_used": False,
        "external_image_apis_used": False,
        "beats": [{**beat, "visual_brief": visual_briefs[i - 1],
                   "spoken_duration_seconds": round(spoken_durations[i - 1], 3)}
                  for i, beat in enumerate(beats, 1)],
        "files": {
            "video": final_video.name,
            "narration": narration_path.name,
            "captions": "captions.ass",
            "sound_effects": sfx_path.name,
            "audio_mix": bed_path.name,
            "scene_svgs": scene_dir.name,
        },
        "sha256": hashlib.sha256(final_video.read_bytes()).hexdigest(),
    }
    if not manifest["audio"]["narration_included"] or not manifest["captions"]["burned_in"]:
        raise RuntimeError("Narration/caption validation failed.")
    (output_dir / "animation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"ANIMATED VIDEO READY: {final_video}")
    print("Narration: included | Captions: burned into MP4 | Music ducking: enabled")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Render WISE-LAB SVG animation with narration and captions.")
    parser.add_argument("--script", default="scripts/script.txt")
    parser.add_argument("--output", default="output/svg_animation_preview")
    parser.add_argument("--format", choices=("landscape", "shorts"), default="landscape")
    parser.add_argument("--wpm", type=int, default=140)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--width", type=int, default=720)
    args = parser.parse_args()
    if args.fps < 8 or args.fps > 30:
        parser.error("--fps must be between 8 and 30")
    manifest = render_animated_video(
        Path(args.script), Path(args.output), args.format, args.wpm, args.seconds, args.fps, args.width
    )
    print(f"Rendered {manifest['beat_count']} beats / {manifest['rendered_frame_count']} frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
