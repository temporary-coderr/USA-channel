from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


def _difference_hash(image: Image.Image) -> str:
    gray = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{bits:016x}"


def _hash_image(path: Path) -> str:
    with Image.open(path) as image:
        return _difference_hash(image.convert("RGB"))


def visual_fingerprints(path: Path, is_video: bool) -> list[str]:
    """Hash a still or three representative video frames."""
    if not is_video:
        return [_hash_image(path)]
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        duration = max(0.1, float(result.stdout.strip()))
    except Exception as exc:
        raise RuntimeError(f"Could not inspect video for visual duplicate detection: {exc}") from exc
    hashes = []
    with tempfile.TemporaryDirectory(prefix="wise_visual_hash_") as temp:
        for index, fraction in enumerate((0.15, 0.50, 0.85)):
            frame = Path(temp) / f"frame_{index}.png"
            timestamp = min(duration * fraction, max(0.0, duration - 0.05))
            extracted = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{timestamp:.3f}", "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=9:8:flags=area", str(frame)],
                capture_output=True, text=True,
            )
            if extracted.returncode == 0 and frame.exists():
                hashes.append(_hash_image(frame))
    if not hashes:
        raise RuntimeError(f"Could not extract frames for visual duplicate detection: {path.name}")
    return hashes


def find_visual_duplicate(candidate_hashes: list[str], previous_hashes: list[str],
                          max_distance: int = 5) -> dict | None:
    """Return a prior frame with a sufficiently close 64-bit difference hash."""
    for candidate in candidate_hashes:
        for previous in previous_hashes:
            try:
                distance = (int(candidate, 16) ^ int(previous, 16)).bit_count()
            except (TypeError, ValueError):
                continue
            if distance <= max_distance:
                return {"distance": distance, "candidate": candidate, "previous": previous}
    return None
