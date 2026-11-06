from __future__ import annotations

import base64
import hashlib
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
        # Keep stock footage moving: aim for roughly 30–35 spoken words per visual.
        if current and word_count + count > 35:
            groups.append(" ".join(current))
            current, word_count = [], 0
        current.append(sentence)
        word_count += count
    if current:
        groups.append(" ".join(current))
    # Typical 1,000–1,350 word scripts now produce about 29–40 visual scenes.
    # Cap extreme scripts at 40 scenes to keep stock searches and render time manageable.
    while len(groups) > 40:
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
        target_area = 1080 * (1920 if vertical else 1080)
        for variant in hit.get("videos", {}).values():
            w, h = variant.get("width", 0), variant.get("height", 0)
            url = variant.get("url")
            if url and w and h and ((h > w) if vertical else (w >= h)):
                variants.append((w * h, url))
        if variants:
            # Prefer the smallest rendition that meets the output resolution to
            # avoid downloading oversized 4K files for every three-second shot.
            above = [item for item in variants if item[0] >= target_area]
            chosen = min(above, key=lambda item: item[0]) if above else max(variants, key=lambda item: item[0])
            candidates.append((chosen[0], {
                "id": asset_id, "url": chosen[1], "type": "video",
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


def pexels_search(endpoint: str, params: dict, key: str) -> dict:
    response = SESSION.get(endpoint, params=params, headers={"Authorization": key}, timeout=60)
    response.raise_for_status()
    return response.json()

def find_pexels_video(query: str, key: str, vertical: bool, used_ids: set[str]) -> dict | None:
    orientation = "portrait" if vertical else "landscape"
    data = pexels_search("https://api.pexels.com/v1/videos/search", {"query": query, "orientation": orientation, "per_page": 80, "page": 1}, key)
    for hit in data.get("videos", []):
        asset_id = f"pexels:{hit.get('id', '')}"
        if asset_id == "pexels:" or asset_id in used_ids:
            continue
        files = []
        for item in hit.get("video_files", []):
            width, height, link = item.get("width") or 0, item.get("height") or 0, item.get("link")
            if link and width and height and ((height > width) if vertical else (width >= height)):
                files.append((width * height, link))
        if files:
            target_area = 1080 * (1920 if vertical else 1080)
            above = [item for item in files if item[0] >= target_area]
            chosen = min(above, key=lambda item: item[0]) if above else max(files, key=lambda item: item[0])
            user = hit.get("user") or {}
            return {"id": asset_id, "url": chosen[1], "type": "video", "source": "Pexels", "query": query, "page_url": hit.get("url", ""), "creator": user.get("name", ""), "creator_url": user.get("url", "")}
    return None

def find_pexels_image(query: str, key: str, vertical: bool, used_ids: set[str]) -> dict | None:
    orientation = "portrait" if vertical else "landscape"
    data = pexels_search("https://api.pexels.com/v1/search", {"query": query, "orientation": orientation, "per_page": 80, "page": 1}, key)
    for hit in data.get("photos", []):
        asset_id = f"pexels:{hit.get('id', '')}"
        src = hit.get("src") or {}
        url = src.get("large2x") or src.get("large")
        if url and asset_id != "pexels:" and asset_id not in used_ids:
            return {"id": asset_id, "url": url, "type": "image", "source": "Pexels", "query": query, "page_url": hit.get("url", ""), "creator": hit.get("photographer", ""), "creator_url": hit.get("photographer_url", "")}
    return None

def find_openverse_image(query: str, vertical: bool, used_ids: set[str]) -> dict | None:
    """Find openly licensed commercial-use still images as a no-key fallback."""
    response = SESSION.get(
        "https://api.openverse.org/v1/images/",
        params={
            "q": query,
            "license": "cc0,by",
            "license_type": "commercial,modification",
            "size": "large",
            "aspect_ratio": "tall" if vertical else "wide",
            "page_size": 20,
            "filter_dead": "true",
            "mature": "false",
        },
        timeout=35,
    )
    response.raise_for_status()
    for hit in response.json().get("results", []):
        asset_id = "openverse:" + str(hit.get("id") or "")
        url = hit.get("url")
        if not url or asset_id == "openverse:" or asset_id in used_ids:
            continue
        license_code = str(hit.get("license") or "").lower()
        if license_code not in {"cc0", "pdm", "by"}:
            continue
        return {
            "id": asset_id, "url": url, "type": "image", "source": "Openverse",
            "query": query, "page_url": hit.get("foreign_landing_url", ""),
            "title": hit.get("title", "Openly licensed image"),
            "creator": hit.get("creator", "Unknown creator"),
            "creator_url": hit.get("creator_url", ""),
            "license": license_code.upper(),
            "license_version": hit.get("license_version", ""),
            "license_url": hit.get("license_url", ""),
            "attribution": hit.get("attribution", ""),
        }
    return None


def visual_query_from_text(text: str, fallback: str) -> str:
    stop = set("the a an and or but if then than of in on at to for from with by as is are was were be been being it its this that these those you your we our they their he she his her i me my us them what why how when where who which can could would should will just very more most less much many some any not no do does did have has had about into over after before between through during because while also".split())
    terms = []
    for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.lower()):
        if word not in stop and word not in terms:
            terms.append(word)
        if len(terms) >= 6:
            break
    if len(terms) < 2:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", fallback.lower()):
            if word not in stop and word not in terms:
                terms.append(word)
            if len(terms) >= 6:
                break
    return " ".join(terms) or "human psychology everyday life"


def build_ai_image_prompt(shot_text: str, query: str, vertical: bool, groq_key: str = "") -> str:
    """Create a concise, editorially useful visual prompt; Groq refines it when configured."""
    base = (
        "Create a photorealistic cinematic documentary still for a premium US psychology "
        "YouTube explainer. Show a believable everyday human situation that visually "
        "communicates this idea: " + shot_text[:700] + ". "
        "Visual subject keywords: " + query + ". "
        "Use natural human expressions, realistic anatomy, subtle emotion, tasteful "
        "cinematic lighting, authentic contemporary environments, clear composition, "
        "editorial photography, nuanced colors, and a visually interesting foreground. "
        "No text, no letters, no logos, no watermark, no infographic, no collage, "
        "no split screen, no exaggerated facial expressions, no surreal anatomy."
    )
    if groq_key:
        try:
            response = SESSION.post(
                GROQ_URL,
                headers={"Authorization": "Bearer " + groq_key, "Content-Type": "application/json"},
                json={
                    "model": "openai/gpt-oss-20b",
                    "messages": [
                        {"role": "system", "content": "You are a senior documentary art director. Return only one polished image-generation prompt. Do not add text or facts to the image. Preserve the meaning; never depict a real identifiable public figure."},
                        {"role": "user", "content": base + (" Compose for a vertical 9:16 frame." if vertical else " Compose for a wide 16:9 frame.")},
                    ],
                    "temperature": 0.5,
                    "max_completion_tokens": 220,
                },
                timeout=45,
            )
            response.raise_for_status()
            refined = response.json()["choices"][0]["message"]["content"].strip()
            if len(refined) >= 80:
                return refined[:1800]
        except Exception as exc:
            print(f"Groq prompt refinement unavailable; using local prompt: {exc}")
    return base + (" Compose for a vertical 9:16 frame." if vertical else " Compose for a wide 16:9 frame.")


def generate_openai_image(prompt: str, destination: Path, api_key: str, vertical: bool) -> dict:
    """Generate one custom still with the OpenAI Images API, with bounded retries."""
    endpoint = "https://api.openai.com/v1/images/generations"
    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare").strip() or "gpt-image-2.5-flare"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": "864x1536" if vertical else "1536x864",
        "quality": os.getenv("OPENAI_IMAGE_QUALITY", "medium").strip() or "medium",
        "output_format": "webp",
        "output_compression": 88,
        "n": 1,
    }
    last_error = None
    for attempt in range(3):
        try:
            response = SESSION.post(
                endpoint,
                headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=(20, 240),
            )
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = RuntimeError(f"OpenAI image API HTTP {response.status_code}: {response.text[:500]}")
                if attempt < 2:
                    import time
                    time.sleep(2 ** (attempt + 1))
                    continue
            response.raise_for_status()
            body = response.json()
            items = body.get("data") or []
            encoded = items[0].get("b64_json") if items else None
            if not encoded:
                raise RuntimeError("OpenAI image API returned no base64 image data.")
            raw = base64.b64decode(encoded)
            if len(raw) < 4000:
                raise RuntimeError("OpenAI returned an unexpectedly small image.")
            actual_destination = destination.with_suffix(".webp")
            actual_destination.write_bytes(raw)
            return {"path": actual_destination, "mime_type": "image/webp", "model": model}
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                import time
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"OpenAI image generation failed after 3 attempts: {last_error}")

def choose_ai_shot_indices(total_shots: int, requested: int = 6) -> set[int]:
    """Distribute 5–7 AI stills evenly across the full video."""
    if total_shots <= 0:
        return set()
    count = min(total_shots, max(5, min(7, requested)))
    if count == total_shots:
        return set(range(total_shots))
    return {min(total_shots - 1, int((i + 0.5) * total_shots / count)) for i in range(count)}



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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media:
        for chunk in iter(lambda: media.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    """Generate a complete scene with Edge-TTS, retrying transient failures and trying backup voices."""
    import asyncio
    import edge_tts

    primary = os.getenv("EDGE_TTS_VOICE", "en-US-AndrewNeural").strip() or "en-US-AndrewNeural"
    configured = os.getenv("EDGE_TTS_FALLBACK_VOICES", "en-US-GuyNeural,en-US-BrianNeural")
    voices = list(dict.fromkeys([primary] + [v.strip() for v in configured.split(",") if v.strip()]))
    rate = os.getenv("EDGE_TTS_RATE", "+5%").strip() or "+5%"
    chunks = split_tts_text(text)
    if not chunks:
        raise RuntimeError(f"Scene {scene_number} has no narration text.")

    async def generate_with_voice(voice: str) -> list[Path]:
        paths = []
        for chunk_index, chunk in enumerate(chunks, 1):
            chunk_path = WORK / f"edge_voice_scene_{scene_number:02}_part_{chunk_index:02}.mp3"
            chunk_path.unlink(missing_ok=True)
            last_error = None
            for attempt in range(1, 4):
                try:
                    print(f"Edge-TTS scene {scene_number}, chunk {chunk_index}/{len(chunks)}, voice {voice}, attempt {attempt}/3")
                    await edge_tts.Communicate(chunk, voice, rate=rate).save(str(chunk_path))
                    if not chunk_path.exists() or chunk_path.stat().st_size < 1000:
                        raise RuntimeError("Edge-TTS returned an empty or incomplete MP3.")
                    paths.append(chunk_path)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    chunk_path.unlink(missing_ok=True)
                    if attempt < 3:
                        await asyncio.sleep(2 ** attempt)
            if last_error is not None:
                raise RuntimeError(
                    f"Edge-TTS failed for scene {scene_number}, chunk {chunk_index}, voice {voice}: {last_error}"
                ) from last_error
        return paths

    errors = []
    chunk_paths = []
    for voice in voices:
        try:
            # Regenerate the entire scene with one voice to avoid mixing voices between chunks.
            chunk_paths = asyncio.run(generate_with_voice(voice))
            print(f"Edge-TTS narration ready for scene {scene_number} using {voice}.")
            break
        except Exception as exc:
            errors.append(f"{voice}: {exc}")
            for chunk_index in range(1, len(chunks) + 1):
                (WORK / f"edge_voice_scene_{scene_number:02}_part_{chunk_index:02}.mp3").unlink(missing_ok=True)
            print(f"Voice {voice} failed for scene {scene_number}; trying the next available voice.")
    else:
        raise RuntimeError(
            f"All Edge-TTS voices failed for scene {scene_number}. " + " | ".join(errors)
        )

    if len(chunk_paths) == 1:
        shutil.copy2(chunk_paths[0], destination)
    else:
        concat_file = WORK / f"edge_voice_scene_{scene_number:02}_concat.txt"
        concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunk_paths), encoding="utf-8")
        run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(destination)])
    if not destination.exists() or destination.stat().st_size < 1000:
        raise RuntimeError(f"Final narration MP3 for scene {scene_number} is missing or empty.")


def concatenate_scene_audio(audio_paths: list[Path], destination: Path) -> None:
    concat_file = WORK / "voice_all_scenes.txt"
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in audio_paths), encoding="utf-8")
    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(destination)])


def choose_openverse_music(script: str, destination: Path) -> dict | None:
    """Fetch a distinct, instrumental, commercially usable track from Openverse."""
    history_path = ROOT / "visual_history" / "used_music.json"
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {"tracks": []}
    except (OSError, json.JSONDecodeError):
        history = {"tracks": []}
    recent_ids = {str(item.get("id")) for item in history.get("tracks", [])[-50:]}

    lower = script.lower()
    if any(word in lower for word in ("grief", "lonely", "trauma", "healing", "sadness", "anxiety")):
        mood_queries = ["reflective cinematic piano instrumental", "emotional ambient documentary instrumental"]
        mood = "reflective"
    elif any(word in lower for word in ("fear", "stress", "danger", "overthinking", "manipulation", "mystery")):
        mood_queries = ["subtle suspense cinematic instrumental", "psychological documentary ambient instrumental"]
        mood = "subtle suspense"
    elif any(word in lower for word in ("goal", "habit", "success", "confidence", "discipline", "growth")):
        mood_queries = ["uplifting cinematic documentary instrumental", "inspiring ambient piano instrumental"]
        mood = "uplifting"
    else:
        mood_queries = ["calm cinematic documentary instrumental", "thoughtful ambient piano instrumental"]
        mood = "calm documentary"

    candidates = []
    seen = set()
    for query in mood_queries:
        try:
            response = SESSION.get(
                "https://api.openverse.org/v1/audio/",
                params={
                    "q": query,
                    "category": "music",
                    "license": "cc0,pdm,by",
                    "license_type": "commercial,modification",
                    "length": "long",
                    "page_size": 20,
                    "filter_dead": "true",
                },
                timeout=25,
            )
            response.raise_for_status()
            for item in response.json().get("results", []):
                track_id = str(item.get("id") or "")
                license_code = str(item.get("license") or "").lower()
                tags = " ".join(str(tag.get("name", "")) for tag in item.get("tags", []) if isinstance(tag, dict)).lower()
                title = str(item.get("title") or "Untitled instrumental")
                if (not track_id or track_id in seen or license_code not in {"cc0", "pdm", "by"}
                        or not item.get("url") or not item.get("foreign_landing_url")
                        or any(term in (title + " " + tags).lower() for term in ("vocal", "singing", "spoken word", "speech"))):
                    continue
                seen.add(track_id)
                candidates.append(item)
        except Exception as exc:
            print(f"Openverse music search unavailable for '{query}': {exc}")

    fresh = [item for item in candidates if str(item.get("id")) not in recent_ids]
    if not fresh:
        print("WARNING: No unused, suitably licensed Openverse music track was available. Rendering narration without BGM rather than using the old synthetic tone.") 
        return None
    # Pick a track deterministically from the current script, so reruns are stable.
    seed = int(hashlib.sha256(script.encode("utf-8")).hexdigest()[:8], 16)
    selected = fresh[seed % len(fresh)]
    response = SESSION.get(selected["url"], stream=True, timeout=60)
    response.raise_for_status()
    total = 0
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            total += len(chunk)
            if total > 60 * 1024 * 1024:
                handle.close()
                destination.unlink(missing_ok=True)
                raise RuntimeError("Selected background music exceeded the 60 MB safety limit.")
            handle.write(chunk)
    if total < 20_000:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Openverse returned an unexpectedly small music file.")
    track = {
        "id": str(selected["id"]),
        "title": str(selected.get("title") or "Untitled"),
        "creator": str(selected.get("creator") or "Unknown creator"),
        "creator_url": str(selected.get("creator_url") or ""),
        "landing_url": str(selected["foreign_landing_url"]),
        "license": str(selected.get("license") or "").upper(),
        "license_version": str(selected.get("license_version") or ""),
        "license_url": str(selected.get("license_url") or "https://creativecommons.org/"),
        "attribution": str(selected.get("attribution") or ""),
        "mood": mood,
    }
    history.setdefault("tracks", []).append(track)
    history["tracks"] = history["tracks"][-100:]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Selected Openverse background track: {track['title']} — {track['creator']} ({track['license']})")
    return track


def mix_background_music(voice_track: Path, music_file: Path, destination: Path) -> None:
    """Mix a licensed music track quietly beneath narration with automatic voice ducking."""
    ff = ffmpeg()
    duration = probe_duration(voice_track)
    fade_out = max(0.1, duration - 1.5)
    filter_graph = (
        "[1:a]volume=0.24,highpass=f=75,lowpass=f=14000,"
        f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.3f}:d=1.5[music];"
        "[music][0:a]sidechaincompress=threshold=0.035:ratio=9:"
        "attack=20:release=650:makeup=1[ducked];"
        "[0:a][ducked]amix=inputs=2:weights='1 0.55':normalize=0,"
        "alimiter=limit=0.95:level=disabled[a]"
    )
    run([
        ff, "-y", "-i", str(voice_track), "-stream_loop", "-1", "-i", str(music_file),
        "-filter_complex", filter_graph,
        "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{duration:.3f}", "-movflags", "+faststart", str(destination)
    ])


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def make_captions(scenes: list[dict], path: Path, durations: list[float], offset: float = 0.0) -> None:
    """Write a standard SRT sidecar; timings are phrase-level estimates."""
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
            entries.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{' '.join(chunk)}")
            index += 1
            cursor = end
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360000)
    minutes, centiseconds = divmod(centiseconds, 6000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{centiseconds:02}"


def make_highlight_captions(scenes: list[dict], path: Path,
                            durations: list[float], vertical: bool,
                            offset: float = 0.0) -> None:
    """Create readable ASS captions with a teal karaoke highlight on each estimated spoken word."""
    font_size = 54 if vertical else 48
    margin_v = 170 if vertical else 88
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {1080 if vertical else 1920}\n"
        f"PlayResY: {1920 if vertical else 1080}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H00D0D639,&HCC07111C,&H6607111C,"
        f"1,0,0,0,100,100,0,0,1,3,1.5,2,100,100,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    cursor = offset
    for scene, duration in zip(scenes, durations):
        words = re.findall(r"\S+", scene["narration"])
        if not words:
            cursor += duration
            continue
        chunks = [words[i:i + 6] for i in range(0, len(words), 6)]
        for chunk in chunks:
            chunk_duration = duration * len(chunk) / len(words)
            start, end = cursor, cursor + chunk_duration
            karaoke = []
            for word in chunk:
                safe_word = word.replace("\\", "").replace("{", "").replace("}", "")
                word_cs = max(1, round((chunk_duration / len(chunk)) * 100))
                karaoke.append(r"{\kf" + str(word_cs) + "}" + safe_word)
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{' '.join(karaoke)}"
            )
            cursor = end
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def merge_scene_transitions(scene_paths: list[Path], durations: list[float],
                            destination: Path) -> None:
    """Join scenes with short cross-dissolves, preserving the full narration runtime."""
    if len(scene_paths) == 1:
        shutil.copy2(scene_paths[0], destination)
        return
    ff = ffmpeg()
    transition = min(0.38, max(0.01, min(durations) * 0.4))
    command = [ff, "-y"]
    for path in scene_paths:
        command += ["-i", str(path)]
    filters = []
    for index in range(len(scene_paths)):
        initial_fade = ",fade=t=in:st=0:d=0.35" if index == 0 else ""
        filters.append(
            f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={FPS},format=yuv420p"
            f"{initial_fade}[v{index}]"
        )
    previous = "v0"
    elapsed = durations[0]
    for index in range(1, len(scene_paths)):
        output = f"x{index}"
        offset = max(0.0, elapsed - transition * index)
        filters.append(
            f"[{previous}][v{index}]xfade=transition=fade:duration={transition}:"
            f"offset={offset:.3f}[{output}]"
        )
        previous = output
        elapsed += durations[index]
    overlap = transition * (len(scene_paths) - 1)
    filters.append(f"[{previous}]tpad=stop_mode=clone:stop_duration={overlap:.3f},format=yuv420p[outv]")
    command += [
        "-filter_complex", ";".join(filters), "-map", "[outv]",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination)
    ]
    run(command)


def prepare_wise_lab_character(work_dir: Path) -> dict[str, Path]:
    """Render four original transparent SVG poses for the recurring WISE LAB guide."""
    converter = shutil.which("rsvg-convert")
    if not converter:
        raise RuntimeError("rsvg-convert is required for the WISE LAB 2D character. Install librsvg2-bin.")
    target = work_dir / "wise_lab_character"
    target.mkdir(parents=True, exist_ok=True)
    poses = {
        "explaining": (
            '<path d="M168 468 Q105 520 128 620 L155 660" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<path d="M350 465 Q405 430 415 365 L426 330" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<circle cx="428" cy="316" r="25" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>'
        ),
        "pointing": (
            '<path d="M168 468 Q105 520 128 620 L155 660" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<path d="M350 465 Q410 450 445 430 L480 420" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<path d="M466 419 L505 408" fill="none" stroke="#E8B98D" stroke-width="17" stroke-linecap="round"/>'
        ),
        "thinking": (
            '<path d="M168 468 Q105 520 128 620 L155 660" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<path d="M350 465 Q405 430 370 350 L330 315" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<circle cx="320" cy="306" r="24" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>'
        ),
        "surprised": (
            '<path d="M168 468 Q95 430 82 350 L75 315" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<circle cx="73" cy="300" r="25" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>'
            '<path d="M350 465 Q425 430 438 350 L445 315" fill="none" stroke="#F1F5F9" stroke-width="42" stroke-linecap="round"/>'
            '<circle cx="447" cy="300" r="25" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>'
        ),
    }
    for name, arms in poses.items():
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="520" height="900" viewBox="0 0 520 900">
<defs>
 <linearGradient id="coat" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFFFFF"/><stop offset="1" stop-color="#DCE7F0"/></linearGradient>
 <linearGradient id="teal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#39D6D0"/><stop offset="1" stop-color="#159B9A"/></linearGradient>
</defs>
<!-- Original WISE LAB guide: transparent background, clean editorial vector style -->
<ellipse cx="260" cy="858" rx="130" ry="19" fill="#071321" opacity=".18"/>
<!-- legs -->
<path d="M205 735 L195 830 Q194 850 218 850 L245 850 L260 744" fill="#23364D"/>
<path d="M285 744 L300 830 Q301 850 324 850 L351 850 Q358 831 337 824 L324 735" fill="#23364D"/>
<path d="M194 838 Q215 827 247 840 L247 861 L184 861 Q180 848 194 838Z" fill="#101F31"/>
<path d="M302 838 Q326 827 351 840 L365 861 L303 861Z" fill="#101F31"/>
<!-- coat silhouette -->
<path d="M176 420 Q130 444 124 535 L139 760 Q260 792 381 760 L396 535 Q390 444 344 420 L305 400 L215 400Z" fill="url(#coat)" stroke="#26364A" stroke-width="9" stroke-linejoin="round"/>
<!-- shirt and collar -->
<path d="M213 405 L260 458 L307 405 L292 390 L228 390Z" fill="#14283E"/>
<path d="M238 414 L260 449 L282 414 L272 400 L248 400Z" fill="url(#teal)"/>
<path d="M260 449 L248 490 L260 515 L272 490Z" fill="#159B9A"/>
<!-- arms, pose-specific -->
{arms}
<!-- coat lapels and pocket -->
<path d="M213 411 L178 475 L218 540 L245 462Z" fill="#FFFFFF" stroke="#26364A" stroke-width="7" stroke-linejoin="round"/>
<path d="M307 411 L342 475 L302 540 L275 462Z" fill="#EAF1F6" stroke="#26364A" stroke-width="7" stroke-linejoin="round"/>
<path d="M305 604 L357 604 L357 670 L305 670Z" fill="#D9E7EF" stroke="#26364A" stroke-width="6"/>
<path d="M316 622 L346 622" stroke="#39D6D0" stroke-width="7" stroke-linecap="round"/>
<text x="330" y="654" font-family="DejaVu Sans, sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#1C5260">WISE</text>
<!-- neck and head -->
<path d="M226 366 L226 418 Q260 450 294 418 L294 366Z" fill="#D99E72" stroke="#26364A" stroke-width="7"/>
<ellipse cx="260" cy="250" rx="111" ry="133" fill="#E8B98D" stroke="#26364A" stroke-width="9"/>
<!-- hair -->
<path d="M150 231 Q135 126 224 112 Q315 84 367 161 Q387 191 369 235 Q351 204 327 193 Q291 218 243 195 Q202 226 150 231Z" fill="#253348" stroke="#17263A" stroke-width="9" stroke-linejoin="round"/>
<path d="M158 220 Q177 177 214 164" fill="none" stroke="#53657A" stroke-width="12" stroke-linecap="round"/>
<!-- ears -->
<ellipse cx="150" cy="263" rx="18" ry="29" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>
<ellipse cx="370" cy="263" rx="18" ry="29" fill="#E8B98D" stroke="#26364A" stroke-width="7"/>
<!-- glasses -->
<g fill="none" stroke="#23364D" stroke-width="8">
 <rect x="177" y="238" width="72" height="54" rx="18"/>
 <rect x="271" y="238" width="72" height="54" rx="18"/>
 <path d="M249 258 Q260 249 271 258"/>
</g>
<!-- eyes and brows -->
<path d="M193 225 Q211 214 231 224 M289 224 Q310 214 328 225" fill="none" stroke="#26364A" stroke-width="8" stroke-linecap="round"/>
<ellipse cx="214" cy="263" rx="8" ry="11" fill="#17263A"/>
<ellipse cx="306" cy="263" rx="8" ry="11" fill="#17263A"/>
<path d="M260 268 L250 310 L267 313" fill="none" stroke="#B77958" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M235 340 Q260 358 285 340" fill="none" stroke="#8F4D47" stroke-width="7" stroke-linecap="round"/>
<!-- subtle cheek accents -->
<ellipse cx="190" cy="316" rx="17" ry="8" fill="#D98278" opacity=".22"/>
<ellipse cx="330" cy="316" rx="17" ry="8" fill="#D98278" opacity=".22"/>
</svg>"""
        svg_path = target / f"{name}.svg"
        png_path = target / f"{name}.png"
        svg_path.write_text(svg, encoding="utf-8")
        run([converter, "-w", "520", "-h", "900", "-o", str(png_path), str(svg_path)])
        if not png_path.exists() or png_path.stat().st_size < 1000:
            raise RuntimeError(f"Could not render WISE LAB character pose: {name}")
    return {name: target / f"{name}.png" for name in poses}


def overlay_wise_lab_character(video: Path, pose_png: Path, seconds: float,
                               width: int, height: int, shot_number: int) -> None:
    """Animate the guide entering, gently bobbing, and exiting over selected shots."""
    vertical = height > width
    character_height = int(height * (0.27 if vertical else 0.44))
    margin = int(width * (0.035 if vertical else 0.025))
    side = "right" if (shot_number // 3) % 2 else "left"
    if side == "left":
        x_expr = (
            f"if(lt(t,0.32),-overlay_w+(overlay_w+{margin})*t/0.32,"
            f"if(gt(t,{seconds:.3f}-0.32),{margin}-(overlay_w+{margin})*(t-({seconds:.3f}-0.32))/0.32,{margin}))"
        )
    else:
        x_expr = (
            f"if(lt(t,0.32),main_w-(overlay_w+{margin})*t/0.32,"
            f"if(gt(t,{seconds:.3f}-0.32),main_w-overlay_w-{margin}+(overlay_w+{margin})*(t-({seconds:.3f}-0.32))/0.32,main_w-overlay_w-{margin}))"
        )
    temp = video.with_name(video.stem + "_character.mp4")
    enable_end = max(0.08, seconds - 0.08)
    filter_graph = (
        f"[1:v]scale=-1:{character_height},format=rgba[guide];"
        f"[0:v][guide]overlay=x='{x_expr}':"
        f"y='H-h-{int(height * 0.035)}+5*sin(2*PI*t*0.8)':"
        f"enable='between(t,0.02,{enable_end:.3f})':format=auto[v]"
    )
    run([
        ffmpeg(), "-y", "-i", str(video), "-loop", "1", "-framerate", str(FPS),
        "-i", str(pose_png), "-filter_complex", filter_graph,
        "-map", "[v]", "-an", "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast" if vertical else "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", str(temp)
    ])
    temp.replace(video)


def render_scene(media: Path, destination: Path, seconds: float,
                 width: int, height: int, is_image: bool) -> None:
    ff = ffmpeg()
    vf_base = (
        f"scale={int(width * 1.08)}:{int(height * 1.08)}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:x='(in_w-out_w)/2+sin(t*0.45)*((in_w-out_w)/4)':"
        f"y='(in_h-out_h)/2+cos(t*0.35)*((in_h-out_h)/5)',setsar=1,fps={FPS},"
        "eq=contrast=1.04:saturation=1.06:brightness=0.01"
    )
    preset = "ultrafast" if FORMAT == "shorts" else "veryfast"
    crf = "22" if FORMAT == "shorts" else "21"
    if is_image:
        # Slow Ken Burns zoom. One output frame is generated for each frame of the scene.
        frames = max(1, round(seconds * FPS))
        zoom = (
            f"scale={int(width * 1.18)}:{int(height * 1.18)}:force_original_aspect_ratio=increase,"
            f"crop={int(width * 1.18)}:{int(height * 1.18)},"
            f"zoompan=z='min(zoom+0.0007,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={FPS},"
            "eq=contrast=1.04:saturation=1.06:brightness=0.01"
        )
        run([ff, "-y", "-loop", "1", "-i", str(media), "-t", f"{seconds:.3f}",
             "-vf", zoom, "-an", "-c:v", "libx264", "-preset", preset,
             "-crf", crf, "-pix_fmt", "yuv420p", str(destination)])
    else:
        # Slight overscale/crop gives stock clips a restrained push-in feel.
        run([ff, "-y", "-stream_loop", "-1", "-i", str(media), "-t", f"{seconds:.3f}",
             "-vf", vf_base, "-an", "-c:v", "libx264", "-preset", preset,
             "-crf", crf, "-pix_fmt", "yuv420p", str(destination)])



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
    subscribe_outro = "SUBSCRIBE" in footer.upper()
    cta_size = int(min(width * 0.040, height * 0.040))
    footer_layer = (
        f"drawbox=x=iw*0.34:y=ih*0.805:w=iw*0.32:h=ih*0.075:"
        f"color=0xFF3045@0.98:t=fill:enable='between(t,1.0,{duration - 0.3:.3f})',"
        f"drawtext=fontfile={font}:text='SUBSCRIBE':fontcolor=white:fontsize={cta_size}:"
        "x=(main_w-text_w)/2:y=main_h*0.824:"
        "alpha='if(lt(t,1.45),max(0,(t-1.0)/0.45),1)':"
        f"enable='between(t,1.0,{duration - 0.3:.3f})'"
    ) if subscribe_outro else (
        f"drawtext=fontfile={regular}:text='{footer}':fontcolor=white@0.78:"
        f"fontsize={footer_size}:x=(main_w-text_w)/2:y=main_h*0.79"
    )
    video_filter = (
        "noise=alls=7:allf=t+u,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x081321@0.18:t=fill,"
        "drawbox=x=iw*0.29:y=ih*0.205:w=iw*0.42:h=3:color=0x39D6D0@0.9:t=fill,"
        f"drawtext=fontfile={font}:text='W':fontcolor=0x39D6D0:fontsize={logo_size}:"
        "x=(main_w-text_w)/2:y=main_h*0.245:shadowcolor=black@0.45:shadowx=2:shadowy=3,"
        f"drawtext=fontfile={font}:text='WISE LAB':fontcolor=white:fontsize={brand_size}:"
        "x=(main_w-text_w)/2:y=main_h*0.445:shadowcolor=black@0.5:shadowx=2:shadowy=3:"
        "alpha='0.88+0.12*sin(2*PI*t)',"
        f"drawtext=fontfile={regular}:text='{subtitle}':fontcolor=0xD5E4EF:"
        f"fontsize={subtitle_size}:x=(main_w-text_w)/2:y=main_h*0.565,"
        f"drawtext=fontfile={font}:text='{headline}':fontcolor=0x39D6D0:"
        f"fontsize={headline_size}:x=(main_w-text_w)/2:y=main_h*0.69,"
        f"{footer_layer},"
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

def make_thumbnail(video_path: Path, destination: Path, title: str, vertical: bool) -> None:
    """Create a branded still thumbnail from the finished render."""
    ff = ffmpeg()
    WORK.mkdir(parents=True, exist_ok=True)
    title_file = WORK / "thumbnail_title.txt"
    title_file.write_text(title.strip()[:90], encoding="utf-8")
    text_path = title_file.resolve().as_posix().replace(":", r"\:")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    seek = "0.5" if vertical else "5.5"
    width, height = (1080, 1920) if vertical else (1280, 720)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        "drawbox=x=0:y=ih*0.57:w=iw:h=ih*0.43:color=0x081321@0.78:t=fill,"
        f"drawtext=fontfile={font}:textfile='{text_path}':fontcolor=white:"
        f"fontsize={72 if vertical else 58}:line_spacing=12:"
        "x=(w-text_w)/2:y=h-text_h-90"
    )
    run([ff, "-y", "-ss", seek, "-i", str(video_path), "-frames:v", "1",
         "-vf", vf, "-q:v", "2", str(destination)])
    if not destination.exists() or destination.stat().st_size < 4000:
        raise RuntimeError("Thumbnail generation failed or produced an empty image.")


def make_video_title(script: str) -> str:
    """Choose a human-readable title from the script hook instead of the channel greeting."""
    clean = re.sub(r"\s+", " ", script).strip()
    patterns = [
        r"(?:today,?\s+i['’]m\s+)?breaking down\s+(.+?)(?:[.!?]|$)",
        r"(?:today,?\s+we(?:'re| are)\s+looking at\s+)(.+?)(?:[.!?]|$)",
    ]
    candidate = ""
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" \"'.,!?")
            break
    if not candidate:
        sentences = [s.strip() for s in re.findall(r"[^.!?]+[.!?]+", clean)]
        candidate = next((s for s in sentences if "?" in s and "welcome to" not in s.lower()), "")
    if not candidate:
        candidate = "Psychology That Helps You Understand Yourself"
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if len(candidate) > 88:
        candidate = candidate[:85].rsplit(" ", 1)[0].rstrip(" ,:;") + "…"
    return candidate[:100]


def make_video_description(title: str, scenes: list[dict], durations: list[float],
                           vertical: bool, assets: list[dict] | None = None,
                           music_info: dict | None = None) -> str:
    lines = [
        title, "",
        "Welcome to WISE LAB — clear, thoughtful explainers about psychology, human behaviour,",
        "and the habits that shape everyday life.", "",
        "In this video, we explore the ideas behind the topic and practical questions you can",
        "use to reflect on your own experiences.", "", "CHAPTERS",
    ]
    cursor = 0.0 if vertical else 5.0
    for scene, duration in zip(scenes, durations):
        total = int(cursor)
        stamp = f"{total // 60}:{total % 60:02}"
        heading = re.sub(r"\s+", " ", str(scene.get("heading") or "Key idea")).strip()
        lines.append(f"{stamp} {heading[:65].rstrip(' ,:;.-')}")
        cursor += duration
    credits = []
    for asset in assets or []:
        source = (asset.get("source") or "Pixabay").lower()
        if source == "pexels":
            creator = asset.get("creator") or "Pexels contributor"
            creator_url = asset.get("creator_url") or asset.get("page_url") or "https://www.pexels.com/"
            credits.append(f"Photo/video by {creator} on Pexels: {creator_url}")
        elif source == "openverse":
            credits.append(
                asset.get("attribution") or
                f'"{asset.get("title", "Image")}" by {asset.get("creator", "Unknown creator")} '
                f'— {asset.get("license", "CC BY")} {asset.get("license_version", "")}. '
                f'{asset.get("page_url", "")} Licence: {asset.get("license_url", "")}'
            )
        elif source.startswith("openai"):
            credits.append("AI-generated visual created with OpenAI GPT Image (not stock footage).")
        else:
            credits.append(f"Pixabay media: {asset.get('page_url') or 'https://pixabay.com/'}")
    if credits:
        lines += ["", "VISUAL CREDITS"] + list(dict.fromkeys(credits))
    if music_info:
        music_credit = music_info.get("attribution") or (
            f'"{music_info.get("title", "Background music")}" by {music_info.get("creator", "Unknown creator")}'
            f' — {music_info.get("license", "Creative Commons")} {music_info.get("license_version", "")}.'
            f' Source: {music_info.get("landing_url", "")}'
        )
        lines += ["", "BACKGROUND MUSIC CREDITS", music_credit,
                  f"Track page: {music_info.get('landing_url', '')}",
                  f"Licence: {music_info.get('license', '')} {music_info.get('license_version', '')} — {music_info.get('license_url', '')}"]
    lines += [
        "", "WISE LAB shares educational content for general information and self-reflection.",
        "It is not medical advice or a substitute for care from a qualified professional.", "",
        "What stood out to you? Share your perspective respectfully in the comments.",
        "Subscribe to WISE LAB for more psychology and human-behaviour explainers.", "",
        "#WiseLab #Psychology #HumanBehaviour",
    ]
    return "\n".join(lines) + "\n"


def make_editorial_review(script: str, destination: Path) -> None:
    """Flag claims a human editor should verify; these flags are not fact-checks."""
    patterns = [
        (r"\b\d+(?:%| percent)\b", "Specific percentage/statistic: verify the original study and population."),
        (r"\b(?:study|research|researchers|survey|tracked|tracking|found)\b", "Research claim: add a traceable source before publication."),
        (r"\b(?:Stanford|Harvard|Yale|Oxford|University of|American Psychological Association)\b",
         "Institution named: verify the exact publication, date and wording."),
        (r"\b(?:proves?|guarantees?|always|never|number one predictor|unbreakable)\b",
         "Absolute or causal wording: check whether the evidence supports this strength of claim."),
    ]
    findings = []
    for pattern, note in patterns:
        if re.search(pattern, script, flags=re.IGNORECASE) and note not in findings:
            findings.append(note)
    report = [
        "WISE LAB — EDITORIAL REVIEW", "",
        "Automated pre-publication flags only. This is NOT a fact-check and does not verify sources.",
        "A human editor should review every named study, statistic, quotation and causal claim.", "",
    ] + [f"- {item}" for item in findings]
    if not findings:
        report.append("- No obvious trigger phrases detected; this does not establish factual accuracy.")
    report += [
        "", "Before publishing: confirm quotations against primary sources, avoid overstating correlations,",
        "and ensure stock footage and captions match the narration.",
    ]
    destination.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    if not SCRIPT.exists():
        raise RuntimeError(f"Script file not found: {SCRIPT}. Upload your text to scripts/script.txt.")
    script = SCRIPT.read_text(encoding="utf-8").strip()
    script = re.sub(r"\[EXTRO\]", "", script, flags=re.IGNORECASE).strip()
    word_count = len(script.split())
    if word_count < 100:
        raise RuntimeError(f"Script is too short ({word_count} words). Add at least 100 words.")

    # YouTube Shorts are limited to 3 minutes. Keep a safety margin at 140 WPM
    # so a vertical upload is not accidentally rendered as a regular long video.
    if FORMAT == "shorts" and word_count > 400:
        estimated_minutes = word_count / 140
        raise RuntimeError(
            f"This script has {word_count} words (about {estimated_minutes:.1f} minutes at 140 WPM). "
            "That is too long for a YouTube Short. Choose landscape for this script, "
            "or prepare a Shorts script of 400 words or fewer."
        )
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    vertical = FORMAT == "shorts"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    key = required_env("PIXABAY_API_KEY")
    pexels_key = os.getenv("PEXELS_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    print("Optional Pexels fallback enabled." if pexels_key else "Pexels fallback not configured; using Pixabay only.")
    print("Selective OpenAI GPT Image generation enabled (5–7 images)." if openai_key else "OpenAI image generation disabled; OPENAI_API_KEY is not configured.")
    print("Groq art-direction prompt refinement enabled." if groq_key else "Groq prompt refinement disabled; local prompts will be used.")
    # Scene planning stays local; OpenAI/Groq are used only for selected custom stills.
    plan = plan_scenes(script)
    history, historical_ids = load_visual_history()
    used_ids = set(historical_ids)
    used_hashes = {str(item.get('sha256')) for item in history.get('assets', []) if item.get('sha256')}
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
    music_file = WORK / "wise_lab_background_music"
    mixed_voice_track = WORK / "wise_lab_voice_with_bgm.m4a"
    try:
        music_info = choose_openverse_music(script, music_file)
    except Exception as exc:
        print(f"WARNING: Could not retrieve a suitable licensed music track: {exc}")
        music_info = None
    if music_info:
        print(f"Mixing rotating {music_info['mood']} music under narration with voice ducking...")
        mix_background_music(voice_track, music_file, mixed_voice_track)
        credit_text = (
            (music_info.get("attribution") or music_info["title"] + " by " + music_info["creator"])
            + "\nTrack: " + music_info["landing_url"]
            + "\nCreator: " + music_info["creator"] + " — " + music_info["creator_url"]
            + "\nLicence: " + music_info["license"] + " " + music_info["license_version"]
            + " — " + music_info["license_url"] + "\n"
        )
    else:
        print("Continuing without BGM; the old synthetic tone has been removed.")
        shutil.copy2(voice_track, mixed_voice_track)
        credit_text = "No background music was added: no suitable unused track was available.\n"
    (OUT / "background_music_credit.txt").write_text(credit_text, encoding="utf-8")
    rendered = []
    character_poses = prepare_wise_lab_character(WORK)
    print("Original WISE LAB 2D guide enabled: rotating poses, alternating sides, animated entrance and subtle movement.")

    shot_number = 0
    target_shot_seconds = 3.0
    estimated_shot_counts = [
        min(max(1, int((seconds + target_shot_seconds - 0.001) // target_shot_seconds)),
            max(1, len(re.findall(r"\S+", scene["narration"]))))
        for scene, seconds in zip(plan["scenes"], durations)
    ]
    total_shots = sum(estimated_shot_counts)
    ai_shot_indices = choose_ai_shot_indices(
        total_shots, int(os.getenv("AI_IMAGES_PER_VIDEO", "6"))
    ) if openai_key else set()
    print(f"Planning {len(ai_shot_indices)} selective AI visuals across {total_shots} stock-style cuts.")
    for index, (scene, seconds) in enumerate(zip(plan["scenes"], durations), 1):
        words = re.findall(r"\S+", scene["narration"])
        if not words:
            words = re.findall(r"\S+", scene.get("heading", "psychology"))
        shot_count = max(1, int((seconds + target_shot_seconds - 0.001) // target_shot_seconds))
        shot_count = min(shot_count, max(1, len(words)))
        shot_paths = []
        shot_durations = []
        for shot_index in range(shot_count):
            left = (shot_index * len(words)) // shot_count
            right = ((shot_index + 1) * len(words)) // shot_count
            shot_words = words[left:right] or words
            shot_text = " ".join(shot_words)
            shot_seconds = seconds * len(shot_words) / max(1, len(words))
            query = visual_query_from_text(shot_text, scene["visual_query"])
            image_query = query + " photography"
            print(f"Scene {index}/{len(plan['scenes'])}, shot {shot_index + 1}/{shot_count}: {query}")
            # Alternate provider priority so a single library does not dominate
            # every cut. Each shot gets a fresh, narration-specific search.
            provider_order = ("pixabay", "pexels") if shot_number % 2 == 0 else ("pexels", "pixabay")
            asset = None
            source_errors = []
            queries = list(dict.fromkeys([query, f"{query} documentary", scene["visual_query"]]))
            is_image = False

            # Use a small number of bespoke AI stills for abstract psychology concepts
            # while keeping the majority of the edit grounded in real stock footage.
            if openai_key and shot_number in ai_shot_indices:
                prompt = build_ai_image_prompt(shot_text, query, vertical, groq_key)
                try:
                    generated = generate_openai_image(
                        prompt, WORK / f"openai_visual_{shot_number:04}", openai_key, vertical
                    )
                    asset = {
                        "id": f"openai:{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]}",
                        "url": "", "type": "image", "source": "OpenAI GPT Image",
                        "query": query, "page_url": "https://developers.openai.com/api/docs/guides/image-generation",
                        "prompt": prompt, "mime_type": generated["mime_type"],
                        "local_path": str(generated["path"]),
                    }
                    is_image = True
                    print(f"Generated custom OpenAI visual for shot {shot_number + 1}/{total_shots}.")
                except Exception as exc:
                    source_errors.append(f"OpenAI image: {exc}")
                    print(f"WARNING: OpenAI image failed; falling back to stock sources: {exc}")

            for provider in (() if asset else provider_order):
                if provider == "pexels" and not pexels_key:
                    continue
                for candidate_query in queries:
                    try:
                        if provider == "pixabay":
                            asset = find_video(candidate_query, key, vertical, used_ids)
                        else:
                            asset = find_pexels_video(candidate_query, pexels_key, vertical, used_ids)
                    except Exception as exc:
                        source_errors.append(f"{provider} video: {exc}")
                        print(f"{provider} video search failed: {exc}")
                        break
                    if asset:
                        break
                if asset:
                    break

            if not asset:
                image_queries = list(dict.fromkeys([image_query, query, scene.get("image_query", query)]))
                image_providers = ("pixabay", "pexels", "openverse")
                for provider in image_providers:
                    if provider == "pexels" and not pexels_key:
                        continue
                    for candidate_query in image_queries:
                        try:
                            if provider == "pixabay":
                                asset = find_image(candidate_query, key, vertical, used_ids)
                            elif provider == "pexels":
                                asset = find_pexels_image(candidate_query, pexels_key, vertical, used_ids)
                            else:
                                asset = find_openverse_image(candidate_query, vertical, used_ids)
                        except Exception as exc:
                            source_errors.append(f"{provider} image: {exc}")
                            print(f"{provider} image search failed: {exc}")
                            break
                        if asset:
                            is_image = True
                            break
                    if asset:
                        break
            if not asset:
                detail = " | ".join(source_errors[-3:])
                raise RuntimeError(f"No unused visual found for three-second shot '{query}'. " + detail)

            asset["shot_duration_seconds"] = round(shot_seconds, 3)
            asset["scene_number"] = index
            asset["shot_number"] = shot_number + 1
            used_ids.add(str(asset["id"]))
            selected_assets.append(asset)
            scene["visual_asset"] = asset
            suffix = Path(asset["local_path"]).suffix if asset.get("local_path") else (".jpg" if is_image else ".mp4")
            media_path = WORK / f"source_{shot_number:04}{suffix}"
            if asset.get("local_path"):
                shutil.copy2(asset["local_path"], media_path)
            else:
                download(asset["url"], media_path)
            fingerprint = sha256_file(media_path)
            if fingerprint in used_hashes:
                media_path.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Duplicate visual content detected for shot '{query}'. "
                    "The bot stopped rather than reuse a previously downloaded asset."
                )
            asset["sha256"] = fingerprint
            if str(asset.get("source", "")).lower().startswith("openai"):
                asset["id"] = "openai:" + fingerprint[:20]
            used_hashes.add(fingerprint)

            shot_path = WORK / f"scene_{index:02}_shot_{shot_index:02}.mp4"
            render_scene(media_path, shot_path, shot_seconds, width, height, is_image)
            # The guide appears on roughly one in three three-second cuts; it is not a permanent watermark.
            if shot_number % 3 == 1:
                pose_order = ("explaining", "pointing", "thinking", "surprised")
                pose_name = pose_order[(shot_number // 3) % len(pose_order)]
                overlay_wise_lab_character(
                    shot_path, character_poses[pose_name], shot_seconds,
                    width, height, shot_number
                )
            shot_paths.append(shot_path)
            shot_durations.append(shot_seconds)
            shot_number += 1

        scene_path = WORK / f"scene_{index:02}.mp4"
        merge_scene_transitions(shot_paths, shot_durations, scene_path)
        rendered.append(scene_path)

    silent = OUT / "video_base.mp4"
    merge_scene_transitions(rendered, durations, silent)

    captions = OUT / "captions.srt"
    # Long videos have a 5-second branded intro; Shorts start immediately.
    intro_seconds = 0.0 if vertical else 5.0
    make_captions(plan["scenes"], captions, durations, offset=intro_seconds)
    content_captions = WORK / "content_captions.ass"
    make_highlight_captions(plan["scenes"], content_captions, durations, vertical)
    # Export a styled caption sidecar with the long-form intro offset included.
    make_highlight_captions(
        plan["scenes"], OUT / "captions.ass", durations, vertical, offset=intro_seconds
    )
    caption_filter_path = content_captions.resolve().as_posix().replace(":", r"\:")
    caption_filter = f"subtitles='{caption_filter_path}'"
    content_final = WORK / ("content_shorts.mp4" if vertical else "content_landscape.mp4")
    # Shorts use a faster encoder preset to reduce GitHub runner time while
    # retaining 1080x1920, 30 FPS, and high-quality H.264 output.
    caption_preset = "ultrafast" if vertical else "medium"
    caption_crf = "22" if vertical else "20"
    run([ffmpeg(), "-y", "-i", str(silent), "-vf", caption_filter,
         "-an", "-c:v", "libx264", "-preset", caption_preset, "-crf", caption_crf,
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(content_final)])
    voiced_content = WORK / "content_with_edge_voice.mp4"
    run([ffmpeg(), "-y", "-i", str(content_final), "-i", str(mixed_voice_track),
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
            history_item = {key: value for key, value in asset.items() if key not in {"local_path", "url", "prompt"}}
            history_assets.append({
                **history_item,
                "used_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "format": FORMAT,
                "script_file": str(SCRIPT),
            })
            existing_history_ids.add(str(asset["id"]))
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_assets = [
        {key: value for key, value in asset.items() if key != "local_path"}
        for asset in selected_assets
    ]
    (OUT / "visual_manifest.json").write_text(
        json.dumps(manifest_assets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "scene_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    video_title = make_video_title(script)
    (OUT / "title.txt").write_text(video_title + "\n", encoding="utf-8")
    (OUT / "description.txt").write_text(
        make_video_description(video_title, plan["scenes"], durations, vertical, selected_assets, music_info),
        encoding="utf-8"
    )
    (OUT / "voiceover_script.txt").write_text(script + "\n", encoding="utf-8")
    make_editorial_review(script, OUT / "editorial_review.txt")
    thumbnail = OUT / "wise_lab_thumbnail.jpg"
    make_thumbnail(final, thumbnail, video_title, vertical)
    print(f"THUMBNAIL READY: {thumbnail}")
    print(f"VIDEO READY: {final}")
    print(f"Narration generated with Edge-TTS voice: {os.getenv('EDGE_TTS_VOICE', 'en-US-AndrewNeural')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nVIDEO GENERATION FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
