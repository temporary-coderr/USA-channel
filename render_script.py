from __future__ import annotations

import base64
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
HISTORY_FILE = ROOT / "visual_history" / "used_assets.json"
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


SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "narration": {"type": "string"},
                    "visual_query": {"type": "string"},
                    "image_query": {"type": "string"}
                },
                "required": ["heading", "narration", "visual_query", "image_query"],
                "additionalProperties": False
            }
        }
    },
    "required": ["title", "scenes"],
    "additionalProperties": False
}

SCENE_SYSTEM_PROMPT = (
    "You are a documentary video editor. Break the supplied script into 8-14 "
    "chronological visual scenes. Keep every narration sentence in the same order "
    "and do not invent facts. Return JSON only."
)


def scene_prompt(script: str) -> str:
    return (
        "Create a scene plan for this exact script. For every scene provide: "
        "heading, narration (verbatim excerpts, no rewriting), visual_query "
        "(short literal Pixabay stock footage search), and image_query "
        "(short literal photo search). Prefer real-world B-roll and specific actions. "
        "Avoid asking for footage of identifiable real people, logos, or copyrighted characters. "
        "Return an object with a title and scenes array.\n\n"
        "SCRIPT:\n" + script
    )


def normalize_scene_plan(plan: dict, script: str) -> dict:
    if not isinstance(plan, dict):
        raise RuntimeError("Scene planner did not return a JSON object.")
    scenes = plan.get("scenes", [])
    if not isinstance(scenes, list) or not scenes or len(scenes) > 16:
        count = len(scenes) if isinstance(scenes, list) else 0
        raise RuntimeError(f"Scene planner returned {count} scenes; expected 1–16.")
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("visual_query"):
            raise RuntimeError("A scene is missing a visual search query.")
        scene.setdefault("heading", "Scene")
        scene.setdefault("image_query", scene["visual_query"])

    # Expand very short plans into at least five visual segments.
    original_scene_count = len(scenes)
    while len(scenes) < 5:
        source_scene = scenes[(len(scenes) - original_scene_count) % original_scene_count]
        extra_scene = dict(source_scene)
        extra_scene["heading"] = (source_scene.get("heading") or "Scene") + " — continued"
        scenes.append(extra_scene)

    # Assign narration from the original script in order so no spoken content is lost.
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", script.strip())
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if len(sentences) < len(scenes):
        words = script.split()
        chunk_size = max(1, (len(words) + len(scenes) - 1) // len(scenes))
        narration_chunks = [
            " ".join(words[i:i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]
        while len(narration_chunks) < len(scenes):
            narration_chunks.append("")
        narration_chunks = narration_chunks[:len(scenes)]
    else:
        narration_chunks = []
        remaining = sentences[:]
        for scene_index in range(len(scenes)):
            slots_left = len(scenes) - scene_index
            if slots_left == 1:
                group = remaining
            else:
                words_left = sum(len(part.split()) for part in remaining)
                target = max(1, round(words_left / slots_left))
                group = []
                count = 0
                while remaining and (count < target or not group):
                    candidate = remaining[0]
                    if group and count + len(candidate.split()) > target:
                        break
                    group.append(remaining.pop(0))
                    count += len(candidate.split())
            narration_chunks.append(" ".join(group))

    for scene, narration in zip(scenes, narration_chunks):
        scene["narration"] = narration
    plan["title"] = str(plan.get("title") or "WISE LAB video")
    plan["scenes"] = scenes
    return plan


def plan_scenes(script: str) -> dict:
    """Create a deterministic scene plan locally; no external AI planner is required."""
    stop = set("the a an and or but if then than of in on at to for from with by as is are was were be been being it its this that these those you your we our they their he she his her i me my us them what why how when where who which can could would should will just very more most less much many some any not no do does did have has had about into over after before between through during because while also".split())
    sentences = [part.strip() for part in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", script.strip()) if part.strip()]
    if not sentences:
        raise RuntimeError("The script contains no readable sentences.")
    groups, current, word_count = [], [], 0
    for sentence in sentences:
        count = len(sentence.split())
        if current and word_count + count > 65:
            groups.append(" ".join(current))
            current, word_count = [], 0
        current.append(sentence)
        word_count += count
    if current:
        groups.append(" ".join(current))
    while len(groups) > 14:
        merged = []
        for i in range(0, len(groups), 2):
            merged.append((groups[i] + " " + groups[i + 1]).strip() if i + 1 < len(groups) else groups[i])
        groups = merged
    if len(groups) < 5:
        words = script.split()
        count = max(1, (len(words) + 4) // 5)
        groups = [" ".join(words[i:i + count]) for i in range(0, len(words), count)]
        while len(groups) < 5:
            groups.append(groups[-1])
    scenes = []
    for index, narration in enumerate(groups, 1):
        terms = []
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", narration.lower()):
            if word not in stop and word not in terms:
                terms.append(word)
            if len(terms) >= 5:
                break
        query = " ".join(terms) or "human psychology everyday life"
        heading = " ".join(narration.split()[:7]).strip(" ,.!?—-")
        scenes.append({"heading": heading or f"Scene {index}", "narration": narration,
                       "visual_query": query, "image_query": query + " photography"})
    print(f"Local scene planner: created {len(scenes)} scenes; no external AI agent/API used.")
    return {"title": " ".join(script.split()[:10]).strip(" ,.!?") or "WISE LAB", "scenes": scenes}


def load_visual_history() -> tuple[dict, set[str]]:
    if not HISTORY_FILE.exists():
        return {"assets": []}, set()
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise RuntimeError("visual_history/used_assets.json is invalid JSON. Fix or reset this history file.")
    assets = history.get("assets", [])
    return history, {str(item.get("id")) for item in assets if item.get("id") is not None}


def pixabay_search(endpoint: str, params: dict) -> dict:
    response = SESSION.get(endpoint, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def _pick_video_hit(hits: list[dict], used_ids: set[str], vertical: bool, query: str) -> dict | None:
    candidates = []
    for hit in hits:
        asset_id = str(hit.get("id", ""))
        if not asset_id or asset_id in used_ids:
            continue
        variants = []
        for variant in hit.get("videos", {}).values():
            w, h = variant.get("width", 0), variant.get("height", 0)
            url = variant.get("url")
            if url and w and h and ((h > w) if vertical else (w >= h)):
                variants.append((w * h, url))
        if variants:
            variants.sort(reverse=True)
            candidates.append((variants[0][0], {
                "id": asset_id, "url": variants[0][1], "type": "video",
                "query": query, "page_url": hit.get("pageURL", "")
            }))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def find_video(query: str, key: str, vertical: bool, used_ids: set[str]) -> dict | None:
    # Fetch multiple pages so a growing history does not force old footage to be reused.
    for page in range(1, 4):
        data = pixabay_search(PIXABAY_VIDEO, {
            "key": key, "q": query, "video_type": "film",
            "safesearch": "true", "per_page": 200, "page": page,
        })
        asset = _pick_video_hit(data.get("hits", []), used_ids, vertical, query)
        if asset:
            return asset
        if page * 200 >= data.get("totalHits", 0):
            break
    return None


def find_image(query: str, key: str, vertical: bool, used_ids: set[str]) -> dict | None:
    for page in range(1, 4):
        data = pixabay_search(PIXABAY_IMAGE, {
            "key": key, "q": query, "image_type": "photo",
            "safesearch": "true", "per_page": 200, "page": page,
            "orientation": "vertical" if vertical else "horizontal",
        })
        for hit in data.get("hits", []):
            asset_id = str(hit.get("id", ""))
            url = hit.get("largeImageURL")
            if asset_id and asset_id not in used_ids and url:
                return {
                    "id": asset_id, "url": url, "type": "image",
                    "query": query, "page_url": hit.get("pageURL", "")
                }
        if page * 200 >= data.get("totalHits", 0):
            break
    return None


def download(url: str, destination: Path) -> None:
    # Always download the newly selected asset; no local media cache is used.
    with SESSION.get(url, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_content(1024 * 512):
                if chunk:
                    file.write(chunk)
    if destination.stat().st_size < 4000:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded media file is unexpectedly small: {destination.name}")


def probe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is not installed.")
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Could not read media duration: " + result.stderr[-1000:])
    return float(result.stdout.strip())


def split_tts_text(text: str, limit: int = 1800) -> list[str]:
    sentences = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text.strip())
    chunks, current = [], ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence.encode("utf-16-le")) // 2 > limit:
            for word in sentence.split():
                candidate = (current + " " + word).strip()
                if len(candidate.encode("utf-16-le")) // 2 > limit and current:
                    chunks.append(current)
                    current = word
                else:
                    current = candidate
            continue
        candidate = (current + " " + sentence).strip()
        if len(candidate.encode("utf-16-le")) // 2 > limit and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def synthesize_edge_tts(text: str, destination: Path, scene_number: int) -> None:
    """Use the same Edge-TTS fallback voice as the user's working bot.py."""
    import asyncio
    import edge_tts
    voice = os.getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural").strip() or "en-US-AndrewNeural"
    rate = os.getenv("EDGE_TTS_RATE", "+5%").strip() or "+5%"
    chunk_paths = []
    async def generate() -> None:
        for chunk_index, chunk in enumerate(split_tts_text(text), 1):
            chunk_path = WORK / f"edge_voice_scene_{scene_number:02}_part_{chunk_index:02}.mp3"
            await edge_tts.Communicate(chunk, voice, rate=rate).save(str(chunk_path))
            if not chunk_path.exists() or chunk_path.stat().st_size < 1000:
                raise RuntimeError(f"Edge-TTS returned an empty audio file for scene {scene_number}, chunk {chunk_index}.")
            chunk_paths.append(chunk_path)
    asyncio.run(generate())
    if len(chunk_paths) == 1:
        shutil.copy2(chunk_paths[0], destination)
    else:
        concat_file = WORK / f"edge_voice_scene_{scene_number:02}_concat.txt"
        concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunk_paths), encoding="utf-8")
        run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(destination)])


def concatenate_scene_audio(audio_paths: list[Path], destination: Path) -> None:
    concat_file = WORK / "voice_all_scenes.txt"
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in audio_paths), encoding="utf-8")
    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(destination)])


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
    # Preserve narration audio when preparing the branded sequence.
    run([
        ffmpeg(), "-y", "-i", str(content_video),
        "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", str(content_av)
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
    script = re.sub(r"\[EXTRO\]", "", script, flags=re.IGNORECASE).strip()
    if len(script.split()) < 100:
        raise RuntimeError("Script is too short. Add at least 100 words.")
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    vertical = FORMAT == "shorts"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    key = required_env("PIXABAY_API_KEY")
    # Deterministic local scene planning; no Gemini/Groq agent is used.
    plan = plan_scenes(script)
    history, historical_ids = load_visual_history()
    used_ids = set(historical_ids)
    selected_assets = []

    voice_segments = []
    durations = []
    for index, scene in enumerate(plan["scenes"], 1):
        voice_path = WORK / f"voice_scene_{index:02}.mp3"
        print(f"Generating Edge-TTS narration for scene {index}/{len(plan['scenes'])}...")
        synthesize_edge_tts(scene["narration"], voice_path, index)
        voice_segments.append(voice_path)
        durations.append(probe_duration(voice_path))

    voice_track = OUT / "wise_lab_voiceover.mp3"
    concatenate_scene_audio(voice_segments, voice_track)
    rendered = []

    for index, (scene, seconds) in enumerate(zip(plan["scenes"], durations), 1):
        query = re.sub(r"[^a-zA-Z0-9 ]", " ", scene["visual_query"]).strip()[:90]
        image_query = re.sub(r"[^a-zA-Z0-9 ]", " ", scene.get("image_query", query)).strip()[:90]
        print(f"Scene {index}/{len(plan['scenes'])}: {query}")
        # Try the scene's specific query first, then broader alternatives.
        queries = [query, f"{query} documentary", f"{query} lifestyle"]
        asset = None
        for candidate_query in dict.fromkeys(q for q in queries if q.strip()):
            asset = find_video(candidate_query, key, vertical, used_ids)
            if asset:
                break
        is_image = False
        if not asset:
            for candidate_query in dict.fromkeys(q for q in [image_query, query, f"{query} photography"] if q.strip()):
                asset = find_image(candidate_query, key, vertical, used_ids)
                if asset:
                    break
            is_image = asset is not None
        if not asset:
            raise RuntimeError(
                f"No unused Pixabay visual found for scene '{query}'. "
                "No previously used asset was reused; try a more specific or different script."
            )
        used_ids.add(str(asset["id"]))
        selected_assets.append(asset)
        scene["visual_asset"] = asset
        media_path = WORK / f"source_{index:02}.jpg" if is_image else WORK / f"source_{index:02}.mp4"
        download(asset["url"], media_path)

        scene_path = WORK / f"scene_{index:02}.mp4"
        render_scene(media_path, scene_path, seconds, width, height, is_image)
        rendered.append(scene_path)

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in rendered), encoding="utf-8")
    silent = OUT / "video_base.mp4"
    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(silent)])

    captions = OUT / "captions.srt"
    # Long videos have a 5-second branded intro; Shorts start immediately.
    intro_seconds = 0.0 if vertical else 5.0
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
    voiced_content = WORK / "content_with_edge_voice.mp4"
    run([ffmpeg(), "-y", "-i", str(content_final), "-i", str(voice_track),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-shortest", "-movflags", "+faststart", str(voiced_content)])

    final = OUT / ("wise_lab_shorts.mp4" if vertical else "wise_lab_video.mp4")
    if vertical:
        shutil.copy2(voiced_content, final)
        print("SHORTS MODE: Edge-TTS narration included; skipped intro/outro.")
    else:
        add_wise_lab_branding(voiced_content, final, width, height)
        print("LONG VIDEO MODE: Edge-TTS narration and WISE LAB intro/outro included.")

    # Persist asset IDs only after the complete video has rendered successfully.
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history_assets = history.setdefault("assets", [])
    existing_history_ids = {str(item.get("id")) for item in history_assets if item.get("id") is not None}
    for asset in selected_assets:
        if str(asset["id"]) not in existing_history_ids:
            history_assets.append({
                **asset,
                "used_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "format": FORMAT,
                "script_file": str(SCRIPT),
            })
            existing_history_ids.add(str(asset["id"]))
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "visual_manifest.json").write_text(
        json.dumps(selected_assets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "scene_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "title.txt").write_text(plan.get("title", "WISE LAB video") + "\n", encoding="utf-8")
    (OUT / "voiceover_script.txt").write_text(script + "\n", encoding="utf-8")
    print(f"VIDEO READY: {final}")
    print(f"Narration generated with Edge-TTS voice: {os.getenv('EDGE_TTS_VOICE', 'en-US-AndrewNeural')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nVIDEO GENERATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
