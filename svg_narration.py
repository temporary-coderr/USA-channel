from __future__ import annotations

"""Edge-TTS narration and phrase-synchronous ASS captions for WISE-LAB."""

import asyncio
import re
import shutil
import subprocess
from pathlib import Path


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required to measure narration segments.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


async def _synthesize(text: str, destination: Path, voice: str, rate: str) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("Edge-TTS is required. Install it with: pip install edge-tts") from exc
    await edge_tts.Communicate(text=text, voice=voice, rate=rate).save(str(destination))


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{cs:02d}"


def _caption_text(phrase: str, max_chars: int) -> str:
    words = phrase.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        visible_length = len(re.sub(r"\{[^}]*\}", "", candidate))
        if current and visible_length > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        # The beat planner keeps phrases short; fail rather than silently
        # generating tiny, unreadable captions or dropping spoken words.
        raise RuntimeError(f"Caption phrase needs more than two lines: {phrase!r}")
    return r"\N".join(lines)


def synthesize_beats(beats: list[dict], output_dir: Path, width: int, height: int,
                     voice: str = "en-US-AndrewNeural", rate: str = "+5%") -> tuple[list[Path], list[float], Path]:
    """Synthesize each spoken beat separately so caption times use measured audio."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "narration_segments"
    audio_dir.mkdir(exist_ok=True)
    segment_paths, durations = [], []
    for index, beat in enumerate(beats, 1):
        path = audio_dir / f"narration_{index:04d}.mp3"
        asyncio.run(_synthesize(str(beat["narration"]), path, voice, rate))
        if not path.exists() or path.stat().st_size < 256:
            raise RuntimeError(f"Edge-TTS returned an empty narration segment: {index}")
        duration = probe_duration(path)
        if duration <= 0:
            raise RuntimeError(f"Invalid narration duration for segment {index}")
        segment_paths.append(path)
        durations.append(duration)
        print(f"Generated narration {index}/{len(beats)} ({duration:.2f}s)")
    concat_file = output_dir / "narration_concat.txt"
    concat_file.write_text(
        "".join("file '" + p.resolve().as_posix().replace("'", "'\\''") + "'\n"
                for p in segment_paths), encoding="utf-8"
    )
    narration_path = output_dir / "narration.mp3"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to concatenate narration.")
    _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
          "-safe", "0", "-i", str(concat_file), "-c", "copy", str(narration_path)])

    ass_path = output_dir / "captions.ass"
    play_res_y = height
    font_size = max(26, round(width * (0.068 if height > width else 0.052)))
    margin_v = max(90, round(play_res_y * 0.12))
    max_chars = 27 if play_res_y > width else 46
    rows = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}",
        f"PlayResY: {play_res_y}", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caption,Arial,{font_size},&H00FFFFFF,&H0000D4D4,&H00101B2A,&H99000000,-1,0,0,0,100,100,0,0,1,5,1,2,48,48,{margin_v},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    cursor = 0.0
    for beat, duration in zip(beats, durations):
        phrase = str(beat["narration"]).strip()
        words = phrase.split()
        key_index = max(range(len(words)), key=lambda i: len(re.sub(r"[^A-Za-z]", "", words[i]))) if words else 0
        safe_words = [re.sub(r"([{}])", r"\\\1", word) for word in words]
        if safe_words:
            safe_words[key_index] = r"{\c&H0054D4C8&}" + safe_words[key_index] + r"{\c&H00FFFFFF&}"
        caption_phrase = " ".join(safe_words)
        caption_width = max_chars
        while True:
            try:
                caption = _caption_text(caption_phrase, caption_width)
                break
            except RuntimeError:
                caption_width += 4
                if caption_width > max_chars * 1.6:
                    raise
        if caption_width > max_chars:
            fitted_size = max(24, round(font_size * max_chars / caption_width))
            caption = r"{\fs" + str(fitted_size) + "}" + caption
        start = cursor
        end = cursor + duration
        rows.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Caption,,0,0,0,,"
            + r"{\fad(110,90)}" + caption
        )
        cursor = end
    ass_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    if not narration_path.exists() or not ass_path.exists():
        raise RuntimeError("Narration or caption generation did not produce its required output.")
    return segment_paths, durations, narration_path
