from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SCRIPT_FILE = BASE_DIR / "script.txt"

# VoiceStudio settings supplied for this project.
VOICE_API_URL = os.getenv("VOICESTUDIO_API_URL", "http://localhost:3900")
VOICE_PROFILE_ID = os.getenv("VOICESTUDIO_VOICE_ID", "f90360e8")
VOICE_NAME = os.getenv("VOICESTUDIO_VOICE_NAME", "sndp")
VOICE_MODEL = os.getenv("VOICESTUDIO_MODEL", "omnivoice")
VOICE_LANGUAGE = os.getenv("VOICESTUDIO_LANGUAGE", "English")

PIXABAY_API_URL = "https://pixabay.com/api/videos/"
VIDEO_FORMAT = os.getenv("VIDEO_FORMAT", "landscape").lower()  # landscape or shorts


def run_command(command: list[str]) -> None:
    """Run a process and show useful errors if it fails."""
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"{result.stderr[-4000:]}"
        )


def read_script() -> str:
    if not SCRIPT_FILE.exists():
        raise FileNotFoundError(f"Missing script file: {SCRIPT_FILE}")
    script = SCRIPT_FILE.read_text(encoding="utf-8").strip()
    if not script:
        raise ValueError("script.txt is empty. Add your narration first.")
    return script


def generate_voice(script: str, output_file: Path) -> None:
    speech_url = f"{VOICE_API_URL.rstrip('/')}/v1/audio/speech"
    payload = {
        "model": VOICE_MODEL,
        "input": script,
        "voice": VOICE_PROFILE_ID,
        "response_format": "mp3",
        "language": VOICE_LANGUAGE,
        "speed": 1.0,
    }

    print(f"Connecting to VoiceStudio: {speech_url}")
    try:
        response = requests.post(
            speech_url,
            json=payload,
            headers={"Accept": "audio/mpeg, audio/*, application/json"},
            timeout=(15, 600),
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Cannot reach VoiceStudio. Start VoiceStudio on this PC and "
            f"check {VOICE_API_URL}. A GitHub-hosted runner cannot access "
            "your PC's localhost."
        ) from exc

    print("VoiceStudio HTTP status:", response.status_code)
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:2000]
        raise RuntimeError(f"VoiceStudio API error: {detail}")

    content_type = response.headers.get("Content-Type", "").lower()
    if "json" in content_type or not response.content:
        raise RuntimeError(
            "VoiceStudio did not return audio. "
            f"Content-Type={content_type}; body={response.text[:1000]}"
        )

    output_file.write_bytes(response.content)
    print(f"Voice saved: {output_file} ({len(response.content) / 1024:.1f} KB)")


def search_pixabay_video(api_key: str, query: str) -> str:
    response = requests.get(
        PIXABAY_API_URL,
        params={
            "key": api_key,
            "q": query,
            "video_type": "film",
            "safesearch": "true",
            "per_page": 20,
        },
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    hits = data.get("hits", [])
    if not hits:
        raise RuntimeError(f"Pixabay returned no videos for query: {query}")

    # Prefer a landscape clip for long-form and a portrait clip for Shorts.
    for hit in hits:
        videos = hit.get("videos", {})
        candidates = sorted(
            videos.values(),
            key=lambda item: item.get("width", 0) * item.get("height", 0),
            reverse=True,
        )
        for candidate in candidates:
            width = candidate.get("width", 0)
            height = candidate.get("height", 0)
            if VIDEO_FORMAT == "shorts" and height > width:
                return candidate["url"]
            if VIDEO_FORMAT != "shorts" and width >= height:
                return candidate["url"]

    # Use the largest available result if no orientation match was found.
    hit = hits[0]
    candidates = sorted(
        hit.get("videos", {}).values(),
        key=lambda item: item.get("width", 0) * item.get("height", 0),
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("Pixabay response contained no downloadable video.")
    return candidates[0]["url"]


def download_video(api_key: str, output_file: Path) -> None:
    query = os.getenv("PIXABAY_QUERY", "psychology thinking person brain")
    print(f"Searching Pixabay footage: {query}")
    video_url = search_pixabay_video(api_key, query)

    with requests.get(video_url, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with output_file.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)

    if output_file.stat().st_size < 10_000:
        raise RuntimeError("Downloaded stock video is unexpectedly small.")
    print(f"Footage saved: {output_file}")


def render_video(audio_file: Path, footage_file: Path, output_file: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg was not found. Install FFmpeg and add it to PATH.")

    if VIDEO_FORMAT == "shorts":
        width, height = 1080, 1920
    else:
        width, height = 1920, 1080

    # Loop one stock clip for the full narration duration. The first version
    # intentionally uses a single clip; scene matching and captions come next.
    command = [
        ffmpeg, "-y",
        "-stream_loop", "-1", "-i", str(footage_file),
        "-i", str(audio_file),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(output_file),
    ]
    print("Rendering video with FFmpeg...")
    run_command(command)
    print(f"Video rendered: {output_file}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    script = read_script()

    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not pixabay_key:
        raise RuntimeError(
            "PIXABAY_API_KEY is missing. Set it as an environment variable; "
            "never paste the key into main.py."
        )

    audio_file = OUTPUT_DIR / "narration.mp3"
    footage_file = OUTPUT_DIR / "stock_footage.mp4"
    video_file = OUTPUT_DIR / ("usa_channel_shorts.mp4" if VIDEO_FORMAT == "shorts"
                               else "usa_channel_video.mp4")

    print("=" * 55)
    print("USA-CHANNEL VIDEO AUTOMATION — EXPERIMENT 01")
    print("Voice:", VOICE_NAME, "| Model:", VOICE_MODEL)
    print("Format:", VIDEO_FORMAT)
    print("=" * 55)

    generate_voice(script, audio_file)
    download_video(pixabay_key, footage_file)
    render_video(audio_file, footage_file, video_file)

    print("\nSUCCESS — review the rendered MP4 before publishing.")
    print("Output folder:", OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
