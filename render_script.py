from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SCRIPT = Path(os.getenv("SCRIPT_FILE", "scripts/script.txt"))
OUT = ROOT / "output"
WORK = OUT / "work"
FORMAT = os.getenv("VIDEO_FORMAT", "landscape").lower()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
PIXABAY_VIDEO = "https://pixabay.com/api/videos/"
PIXABAY_IMAGE = "https://pixabay.com/api/"
FPS = 30
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "USA-Channel-VideoMaker/1.0"


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}. Add it under GitHub Settings > Secrets and variables > Actions.")
    return value


def ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is not installed.")
    return path


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Command failed:\n" + result.stderr[-3000:])


def groq_json(script: str) -> dict:
    response = SESSION.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {required_env('GROQ_API_KEY')}"},
        json={
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "temperature": 0.25,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": (
                    "You are a documentary video editor. Break the supplied script into 8-14 "
                    "chronological visual scenes. Keep every narration sentence in the same order "
                    "and do not invent facts. Return JSON only."
                )},
                {"role": "user", "content": (
                    "Create a scene plan for this exact script. For every scene provide: "
                    "heading, narration (verbatim excerpts, no rewriting), visual_query "
                    "(short literal Pixabay stock footage search), and image_query "
                    "(short literal photo search). Prefer real-world B-roll and specific actions. "
                    "Avoid asking for footage of identifiable real people, logos, or copyrighted characters. "
                    "JSON shape: {\"title\":\"...\",\"scenes\":[{\"heading\":\"...\","
                    "\"narration\":\"...\",\"visual_query\":\"...\",\"image_query\":\"...\"}]}\n\n"
                    "SCRIPT:\n" + script
                )},
            ],
        },
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"Groq API error {response.status_code}: {response.text[:1200]}")
    data = response.json()["choices"][0]["message"]["content"]
    plan = json.loads(data)
    scenes = plan.get("scenes", [])
    if not 5 <= len(scenes) <= 16:
        raise RuntimeError(f"Scene planner returned {len(scenes)} scenes; expected 5–16.")
    for scene in scenes:
        if not scene.get("narration") or not scene.get("visual_query"):
            raise RuntimeError("A scene is missing narration or a visual search query.")
    # Prevent a model from silently omitting large parts of the supplied script.
    planned = " ".join(s["narration"] for s in scenes)
    if len(planned.split()) < len(script.split()) * 0.72:
        raise RuntimeError("Scene plan omitted too much of the script. Try again or shorten the script.")
    return plan


def pixabay_search(endpoint: str, params: dict) -> dict:
    response = SESSION.get(endpoint, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def find_video(query: str, key: str, vertical: bool) -> str | None:
    data = pixabay_search(PIXABAY_VIDEO, {
        "key": key, "q": query, "video_type": "film",
        "safesearch": "true", "per_page": 30,
    })
    hits = data.get("hits", [])
    # Prefer a landscape/portrait match and higher resolution, not just the first result.
    candidates = []
    for hit in hits:
        for variant in hit.get("videos", {}).values():
            w, h = variant.get("width", 0), variant.get("height", 0)
            if w and h and ((h > w) if vertical else (w >= h)):
                candidates.append((w * h, variant.get("url")))
    candidates.sort(reverse=True)
    return candidates[0][1] if candidates else None


def find_image(query: str, key: str, vertical: bool) -> str | None:
    data = pixabay_search(PIXABAY_IMAGE, {
        "key": key, "q": query, "image_type": "photo",
        "safesearch": "true", "per_page": 20,
        "orientation": "vertical" if vertical else "horizontal",
    })
    hits = data.get("hits", [])
    return hits[0].get("largeImageURL") if hits else None


def download(url: str, destination: Path) -> None:
    with SESSION.get(url, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_content(1024 * 512):
                if chunk:
                    file.write(chunk)
    if destination.stat().st_size < 4000:
        raise RuntimeError(f"Downloaded media file is unexpectedly small: {destination.name}")


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def make_captions(scenes: list[dict], path: Path, durations: list[float]) -> None:
    entries = []
    index = 1
    cursor = 0.0
    for scene, duration in zip(scenes, durations):
        words = re.findall(r"\S+", scene["narration"])
        chunks = [words[i:i + 6] for i in range(0, len(words), 6)]
        count = max(1, len(words))
        for chunk in chunks:
            start = cursor
            end = cursor + duration * len(chunk) / count
            # Captions are phrase-synced estimates; user can replace with exact timing after voice recording.
            entries.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{' '.join(chunk)}")
            index += 1
            cursor = end
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def render_scene(media: Path, destination: Path, seconds: float,
                 width: int, height: int, is_image: bool) -> None:
    ff = ffmpeg()
    fade_out_start = max(0.0, seconds - 0.35)
    vf_base = (
        f"scale={int(width * 1.08)}:{int(height * 1.08)}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={FPS},"
        "eq=contrast=1.04:saturation=1.06:brightness=0.01,"
        "fade=t=in:st=0:d=0.35,"
        f"fade=t=out:st={fade_out_start:.3f}:d=0.35"
    )
    if is_image:
        # Slow Ken Burns zoom. One output frame is generated for each frame of the scene.
        frames = max(1, round(seconds * FPS))
        zoom = (
            f"scale={int(width * 1.18)}:{int(height * 1.18)}:force_original_aspect_ratio=increase,"
            f"crop={int(width * 1.18)}:{int(height * 1.18)},""
            f"zoompan=z='min(zoom+0.0007,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={FPS},"
            "eq=contrast=1.04:saturation=1.06:brightness=0.01,"
            "fade=t=in:st=0:d=0.35,"
            f"fade=t=out:st={fade_out_start:.3f}:d=0.35"
        )
        run([ff, "-y", "-loop", "1", "-i", str(media), "-t", f"{seconds:.3f}",
             "-vf", zoom, "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "21", "-pix_fmt", "yuv420p", str(destination)])
    else:
        # Slight overscale/crop gives stock clips a restrained push-in feel.
        run([ff, "-y", "-stream_loop", "-1", "-i", str(media), "-t", f"{seconds:.3f}",
             "-vf", vf_base, "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "21", "-pix_fmt", "yuv420p", str(destination)])


def main() -> int:
    if not SCRIPT.exists():
        raise RuntimeError(f"Script file not found: {SCRIPT}. Upload your text to scripts/script.txt.")
    script = SCRIPT.read_text(encoding="utf-8").strip()
    if len(script.split()) < 100:
        raise RuntimeError("Script is too short. Add at least 100 words.")
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    vertical = FORMAT == "shorts"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    key = required_env("PIXABAY_API_KEY")
    plan = groq_json(script)
    (OUT / "scene_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    words = [max(1, len(scene["narration"].split())) for scene in plan["scenes"]]
    # Six-minute target at about 140 spoken words/minute; set TARGET_WPM to adjust.
    wpm = max(90, int(os.getenv("TARGET_WPM", "140")))
    total_duration = sum(words) / wpm * 60
    durations = [total_duration * count / sum(words) for count in words]
    rendered = []

    for index, (scene, seconds) in enumerate(zip(plan["scenes"], durations), 1):
        query = re.sub(r"[^a-zA-Z0-9 ]", " ", scene["visual_query"]).strip()[:90]
        image_query = re.sub(r"[^a-zA-Z0-9 ]", " ", scene.get("image_query", query)).strip()[:90]
        print(f"Scene {index}/{len(plan['scenes'])}: {query}")
        video_url = find_video(query, key, vertical)
        media_path = WORK / f"source_{index:02}.mp4"
        is_image = False
        if video_url:
            download(video_url, media_path)
        else:
            image_url = find_image(image_query or query, key, vertical)
            if not image_url:
                raise RuntimeError(f"No suitable Pixabay video or image found for scene: {query}")
            media_path = WORK / f"source_{index:02}.jpg"
            download(image_url, media_path)
            is_image = True

        scene_path = WORK / f"scene_{index:02}.mp4"
        render_scene(media_path, scene_path, seconds, width, height, is_image)
        rendered.append(scene_path)

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in rendered), encoding="utf-8")
    silent = OUT / "video_base.mp4"
    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(silent)])

    captions = OUT / "captions.srt"
    make_captions(plan["scenes"], captions, durations)
    caption_filter_path = captions.resolve().as_posix().replace(":", r"\:")
    style = (
        "FontName=Arial,FontSize=23,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,"
        "Alignment=2,MarginV=75"
    )
    caption_filter = f"subtitles='{caption_filter_path}':force_style='{style}'"
    final = OUT / ("usa_channel_shorts_silent.mp4" if vertical else "usa_channel_silent.mp4")
    run([ffmpeg(), "-y", "-i", str(silent), "-vf", caption_filter,
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final)])

    (OUT / "title.txt").write_text(plan.get("title", "USA Channel video") + "\n", encoding="utf-8")
    (OUT / "voiceover_script.txt").write_text(script + "\n", encoding="utf-8")
    print(f"VIDEO READY: {final}")
    print("This MP4 has no narration or music. Record your voice and add it during final assembly.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nVIDEO GENERATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
