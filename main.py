from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
TMP = OUT / "scenes"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
PIXABAY_VIDEO = "https://pixabay.com/api/videos/"
PIXABAY_IMAGE = "https://pixabay.com/api/"
VOICE_API = os.getenv("VOICESTUDIO_API_URL", "http://localhost:3900").rstrip("/")
VOICE_ID = os.getenv("VOICESTUDIO_VOICE_ID", "f90360e8")
VOICE_NAME = os.getenv("VOICESTUDIO_VOICE_NAME", "sndp")
VOICE_MODEL = os.getenv("VOICESTUDIO_MODEL", "omnivoice")
FORMAT = os.getenv("VIDEO_FORMAT", "landscape").lower()
DURATION_TARGET = int(os.getenv("TARGET_MINUTES", "6"))
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "USA-Channel-VideoBot/1.0"})


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to GitHub Actions Secrets or your local environment.")
    return value


def groq_chat(messages: list[dict], temperature: float = 0.65) -> str:
    response = SESSION.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {require_env('GROQ_API_KEY')}"},
        json={"model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
              "messages": messages, "temperature": temperature,
              "response_format": {"type": "json_object"}},
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"Groq API {response.status_code}: {response.text[:1500]}")
    return response.json()["choices"][0]["message"]["content"]


def get_topic() -> str:
    topic = os.getenv("VIDEO_TOPIC", "").strip()
    if topic:
        return topic
    prompt = """Choose one compelling, evergreen psychology topic for a high-retention English YouTube channel.
Avoid diagnosis, medical advice, pop-psych myths, sensational claims and topics used in recent generic listicles.
Return JSON only: {"topic":"specific topic","angle":"distinctive angle"}."""
    data = json.loads(groq_chat([{"role": "user", "content": prompt}], 0.9))
    return f"{data['topic']} — {data['angle']}"


def make_content(topic: str) -> dict:
    prompt = f"""
Create a premium, original, fact-conscious YouTube psychology documentary script in English.
Topic: {topic}
Target duration: {DURATION_TARGET} minutes. Aim for {DURATION_TARGET * 125} to {DURATION_TARGET * 145} spoken words.
Audience: general adult viewers. Tone: intelligent, cinematic, empathetic, clear, not clickbait.
Requirements:
- Open with a strong curiosity hook in the first 10 seconds.
- Build a coherent narrative with examples, practical takeaways, and a memorable ending.
- Explain uncertainty; do not invent studies, statistics, quotations, or named researchers.
- Distinguish established findings from hypotheses and avoid diagnosing viewers.
- Include 8 to 12 sequential scenes. Each scene narration should be a self-contained paragraph.
- Each visual_query must be a concise, literal stock-footage search phrase (e.g. "person sitting alone by rainy window").
- Use varied visual concepts and avoid text, logos, celebrities, or copyrighted characters in visual queries.
- Title must be accurate, engaging, and not misleading. Description should include a brief educational disclaimer.
Return valid JSON only with this exact shape:
{{"title":"...","description":"...","tags":["..."],"thumbnail_query":"...","scenes":[{{"heading":"...","narration":"...","visual_query":"..."}}]}}
"""
    raw = groq_chat([{"role": "system", "content": "You are a meticulous documentary writer and fact-checking editor. Output valid JSON only."},
                     {"role": "user", "content": prompt}], 0.55)
    data = json.loads(raw)
    scenes = data.get("scenes", [])
    if len(scenes) < 6:
        raise RuntimeError("The generated script has too few scenes. Retry with a more specific VIDEO_TOPIC.")
    narration = " ".join(s["narration"].strip() for s in scenes)
    words = len(narration.split())
    if words < DURATION_TARGET * 95:
        raise RuntimeError(f"Script too short ({words} words). Increase TARGET_MINUTES or retry.")
    data["full_narration"] = narration
    data["word_count"] = words
    return data


def voiceover(text: str, path: Path) -> None:
    url = f"{VOICE_API}/v1/audio/speech"
    payload = {"model": VOICE_MODEL, "input": text, "voice": VOICE_ID,
               "response_format": "mp3", "language": "English", "speed": 1.0}
    try:
        r = SESSION.post(url, json=payload, headers={"Accept": "audio/mpeg, audio/*"},
                        timeout=(20, 900))
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Cannot reach VoiceStudio at {url}. GitHub-hosted runners cannot reach your PC's localhost. "
            "Use a self-hosted Windows runner on the PC where VoiceStudio is running."
        ) from exc
    if not r.ok or not r.content or "json" in r.headers.get("Content-Type", "").lower():
        raise RuntimeError(f"VoiceStudio failed ({r.status_code}): {r.text[:1200]}")
    path.write_bytes(r.content)


def pixabay_video(query: str, key: str) -> str | None:
    r = SESSION.get(PIXABAY_VIDEO, params={"key": key, "q": query, "video_type": "film",
                    "safesearch": "true", "per_page": 20}, timeout=60)
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        return None
    hits.sort(key=lambda h: h.get("views", 0), reverse=True)
    for hit in hits:
        choices = sorted(hit.get("videos", {}).values(),
                         key=lambda v: v.get("width", 0) * v.get("height", 0), reverse=True)
        for v in choices:
            w, h = v.get("width", 0), v.get("height", 0)
            if (FORMAT == "shorts" and h > w) or (FORMAT != "shorts" and w >= h):
                return v.get("url")
    return next(iter(hits[0].get("videos", {}).values()), {}).get("url")


def pixabay_image(query: str, key: str) -> str | None:
    r = SESSION.get(PIXABAY_IMAGE, params={"key": key, "q": query, "image_type": "photo",
                    "safesearch": "true", "per_page": 20, "orientation": "vertical" if FORMAT == "shorts" else "horizontal"},
                    timeout=60)
    r.raise_for_status()
    hits = r.json().get("hits", [])
    return hits[0].get("largeImageURL") if hits else None


def download(url: str, path: Path) -> None:
    with SESSION.get(url, stream=True, timeout=(20, 180)) as r:
        r.raise_for_status()
        with path.open("wb") as f:
            for chunk in r.iter_content(1024 * 512):
                if chunk:
                    f.write(chunk)
    if path.stat().st_size < 5000:
        raise RuntimeError(f"Downloaded asset is too small: {path}")


def ffmpeg_bin() -> str:
    value = shutil.which("ffmpeg")
    if not value:
        raise RuntimeError("FFmpeg is missing. Install FFmpeg and add it to PATH.")
    return value


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"FFmpeg failed: {p.stderr[-3500:]}")


def srt_time(seconds: float) -> str:
    ms = int(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def make_srt(scenes: list[dict], path: Path, total_duration: float) -> None:
    weights = [max(1, len(s["narration"].split())) for s in scenes]
    total = sum(weights)
    cursor = 0.0
    entries = []
    index = 1
    for scene, weight in zip(scenes, weights):
        duration = total_duration * weight / total
        words = scene["narration"].split()
        # Short readable caption chunks, with timing proportional to word count.
        chunks = [words[i:i + 7] for i in range(0, len(words), 7)]
        for chunk in chunks:
            start = cursor
            end = min(total_duration, cursor + duration * len(chunk) / len(words))
            entries.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{' '.join(chunk)}")
            index += 1
            cursor = end
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def probe_duration(path: Path) -> float:
    p = subprocess.run([ffmpeg_bin().replace("ffmpeg", "ffprobe"), "-v", "error",
        "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        # Fallback to ffmpeg's bundled ffprobe if PATH naming differs.
        probe = shutil.which("ffprobe")
        if not probe:
            raise RuntimeError("ffprobe is required to determine narration duration.")
        p = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True)
        return float(p.stdout.strip())


def render(data: dict, audio: Path, key: str) -> Path:
    OUT.mkdir(exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    duration = probe_duration(audio)
    width, height = (1080, 1920) if FORMAT == "shorts" else (1920, 1080)
    weights = [max(1, len(s["narration"].split())) for s in data["scenes"]]
    total = sum(weights)
    concat_file = TMP / "concat.txt"
    clip_paths = []
    for i, (scene, weight) in enumerate(zip(data["scenes"], weights), 1):
        seconds = duration * weight / total
        q = re.sub(r"[^a-zA-Z0-9 ]", "", scene["visual_query"])[:80]
        print(f"[{i}/{len(data['scenes'])}] Finding visuals: {q}")
        asset = pixabay_video(q, key)
        source = TMP / f"source_{i:02}.mp4"
        still = False
        if asset:
            download(asset, source)
        else:
            image_url = pixabay_image(q, key)
            if not image_url:
                raise RuntimeError(f"No Pixabay video or image found for scene: {q}")
            source = TMP / f"source_{i:02}.jpg"
            download(image_url, source)
            still = True
        clip = TMP / f"clip_{i:02}.mp4"
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30"
        if still:
            cmd = [ff, "-y", "-loop", "1", "-i", str(source), "-t", f"{seconds:.3f}",
                   "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "22", "-pix_fmt", "yuv420p", str(clip)]
        else:
            cmd = [ff, "-y", "-stream_loop", "-1", "-i", str(source), "-t", f"{seconds:.3f}",
                   "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "22", "-pix_fmt", "yuv420p", str(clip)]
        run(cmd)
        clip_paths.append(clip)
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in clip_paths), encoding="utf-8")
    silent = TMP / "silent.mp4"
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c", "copy", str(silent)])
    subtitles = OUT / "captions.srt"
    make_srt(data["scenes"], subtitles, duration)
    video = OUT / ("usa_channel_shorts.mp4" if FORMAT == "shorts" else "usa_channel_video.mp4")
    subtitle_path = subtitles.as_posix().replace(":", r"\\:")
    subtitle_filter = f"subtitles={subtitle_path}:force_style='FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=65'"
    run([ff, "-y", "-i", str(silent), "-i", str(audio), "-vf", subtitle_filter,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", str(video)])
    return video


def main() -> int:
    OUT.mkdir(exist_ok=True)
    key = require_env("PIXABAY_API_KEY")
    topic = get_topic()
    print("Selected topic:", topic)
    data = make_content(topic)
    (OUT / "script.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (OUT / "narration.txt").write_text(data["full_narration"], encoding="utf-8")
    (OUT / "metadata.json").write_text(json.dumps({k: data.get(k) for k in ("title", "description", "tags", "thumbnail_query", "word_count")}, indent=2), encoding="utf-8")
    audio = OUT / "narration.mp3"
    print(f"Generating narration with VoiceStudio profile {VOICE_NAME} ({VOICE_ID})...")
    voiceover(data["full_narration"], audio)
    video = render(data, audio, key)
    print(f"SUCCESS: {video}")
    print(f"Title: {data['title']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nPIPELINE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
