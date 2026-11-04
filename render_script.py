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


def make_captions(scenes: list[dict], path: Path, durations: list[float], offset: float = 0.0) -> None:
    entries = []
    index = 1
    cursor = offset
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
            f"crop={int(width * 1.18)}:{int(height * 1.18)},"
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



def make_brand_clip(destination: Path, duration: float, width: int, height: int,
                    headline: str, subtitle: str, footer: str) -> None:
    """Create an original WISE LAB ident with a custom synthesized ambient music bed."""
    ff = ffmpeg()
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    # The sound is synthesized from simple tones for this channel; no stock music is used.
    audio = (
        "aevalsrc=0.075*sin(2*PI*220*t)+0.055*sin(2*PI*277.18*t)"
        "+0.045*sin(2*PI*329.63*t)+0.025*sin(2*PI*440*t):s=48000:d="
        f"{duration:.3f},"
        f"afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.1, duration - 1.0):.3f}:d=1"
    )
    logo_size = int(min(width * 0.16, height * 0.16))
    brand_size = int(min(width * 0.085, height * 0.085))
    subtitle_size = int(min(width * 0.045, height * 0.033))
    headline_size = int(min(width * 0.045, height * 0.043))
    footer_size = int(min(width * 0.025, height * 0.025))
    video_filter = (
        "noise=alls=7:allf=t+u,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x081321@0.18:t=fill,"
        "drawbox=x=iw*0.29:y=ih*0.205:w=iw*0.42:h=3:color=0x39D6D0@0.9:t=fill,"
        f"drawtext=fontfile={font}:text='W':fontcolor=0x39D6D0:fontsize={logo_size}:"
        "x=(main_w-text_w)/2:y=main_h*0.245:shadowcolor=black@0.45:shadowx=2:shadowy=3,"
        f"drawtext=fontfile={font}:text='WISE LAB':fontcolor=white:fontsize={brand_size}:"
        "x=(main_w-text_w)/2:y=main_h*0.445:shadowcolor=black@0.5:shadowx=2:shadowy=3,"
        f"drawtext=fontfile={regular}:text='{subtitle}':fontcolor=0xD5E4EF:"
        f"fontsize={subtitle_size}:x=(main_w-text_w)/2:y=main_h*0.565,"
        f"drawtext=fontfile={font}:text='{headline}':fontcolor=0x39D6D0:"
        f"fontsize={headline_size}:x=(main_w-text_w)/2:y=main_h*0.69,"
        f"drawtext=fontfile={regular}:text='{footer}':fontcolor=white@0.78:"
        f"fontsize={footer_size}:x=(main_w-text_w)/2:y=main_h*0.79,"
        "fade=t=in:st=0:d=0.65,"
        f"fade=t=out:st={max(0.0, duration - 0.65):.3f}:d=0.65,"
        "format=yuv420p"
    )
    run([
        ff, "-y",
        "-f", "lavfi", "-i", f"color=c=0x081321:s={width}x{height}:r={FPS}:d={duration:.3f}",
        "-f", "lavfi", "-i", audio,
        "-vf", video_filter,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-t", f"{duration:.3f}", "-pix_fmt", "yuv420p",
        str(destination)
    ])


def add_wise_lab_branding(content_video: Path, final_video: Path,
                          width: int, height: int) -> None:
    """Place the same short WISE LAB intro/outro around every finished video."""
    intro_seconds, outro_seconds = 5.0, 7.0
    intro = WORK / "wise_lab_intro.mp4"
    outro = WORK / "wise_lab_outro.mp4"
    content_av = WORK / "content_with_silence.mp4"
    logo_svg = OUT / "wise_lab_logo.svg"
    logo_svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#39D6D0"/><stop offset="1" stop-color="#5577FF"/></linearGradient></defs>
<rect width="800" height="800" rx="180" fill="#081321"/>
<circle cx="400" cy="400" r="285" fill="none" stroke="url(#g)" stroke-width="24"/>
<path d="M190 270 L285 540 L400 355 L515 540 L610 270" fill="none" stroke="url(#g)" stroke-width="48" stroke-linecap="round" stroke-linejoin="round"/>
</svg>""",
        encoding="utf-8"
    )
    make_brand_clip(
        intro, intro_seconds, width, height,
        "EXPLORE THE MIND", "Explore the Mind. Understand Human Behaviour.",
        "PSYCHOLOGY • BEHAVIOUR • EVERYDAY LIFE"
    )
    make_brand_clip(
        outro, outro_seconds, width, height,
        "KEEP THINKING. STAY CURIOUS.", "Understand the mind. Understand the world.",
        "SUBSCRIBE TO WISE LAB"
    )
    # Give the silent main section a silent AAC track so all three sections can be joined cleanly.
    probe = subprocess.run(
        [ffmpeg().replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(content_video)],
        capture_output=True, text=True
    )
    if probe.returncode:
        raise RuntimeError("Could not read the rendered video duration: " + probe.stderr[-1000:])
    content_seconds = float(probe.stdout.strip())
    run([
        ffmpeg(), "-y", "-i", str(content_video),
        "-f", "lavfi", "-t", f"{content_seconds:.3f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(content_av)
    ])
    run([
        ffmpeg(), "-y", "-i", str(intro), "-i", str(content_av), "-i", str(outro),
        "-filter_complex",
        "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(final_video)
    ])

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
    intro_seconds = 5.0
    make_captions(plan["scenes"], captions, durations, offset=intro_seconds)
    content_captions = WORK / "content_captions.srt"
    make_captions(plan["scenes"], content_captions, durations)
    caption_filter_path = content_captions.resolve().as_posix().replace(":", r"\:")
    style = (
        "FontName=Arial,FontSize=23,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,"
        "Alignment=2,MarginV=75"
    )
    caption_filter = f"subtitles='{caption_filter_path}':force_style='{style}'"
    content_final = WORK / ("content_shorts.mp4" if vertical else "content_landscape.mp4")
    run([ffmpeg(), "-y", "-i", str(silent), "-vf", caption_filter,
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(content_final)])
    final = OUT / ("wise_lab_shorts.mp4" if vertical else "wise_lab_video.mp4")
    add_wise_lab_branding(content_final, final, width, height)

    (OUT / "title.txt").write_text(plan.get("title", "WISE LAB video") + "\n", encoding="utf-8")
    (OUT / "voiceover_script.txt").write_text(script + "\n", encoding="utf-8")
    print(f"VIDEO READY: {final}")
    print("WISE LAB intro/outro and original synthesized BGM are included. The main section is silent for your own narration.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nVIDEO GENERATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
