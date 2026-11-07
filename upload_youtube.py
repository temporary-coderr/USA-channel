from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REQUIRED = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


HASHTAG_RE = re.compile(r"(?<![\w])#[\w]+", re.UNICODE)
YOUTUBE_DESCRIPTION_MAX_BYTES = 5000
YOUTUBE_HASHTAG_MAX = 60


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Trim at a valid UTF-8 boundary and avoid leaving a partial final word."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            decoded = clipped.decode("utf-8")
            break
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    else:
        return ""
    if " " in decoded:
        decoded = decoded.rsplit(" ", 1)[0]
    return decoded.rstrip()


def validate_hashtags(title: str, description: str) -> int:
    """Reject metadata with over 60 hashtags; YouTube ignores all of them above this."""
    hashtags = HASHTAG_RE.findall(title + "\n" + description)
    if len(hashtags) > YOUTUBE_HASHTAG_MAX:
        raise RuntimeError(
            f"YouTube hashtag limit exceeded: {len(hashtags)}/{YOUTUBE_HASHTAG_MAX}. "
            "Reduce hashtags in the title/description; upload stopped before sending the video."
        )
    return len(hashtags)


def main() -> int:
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if len(missing) == len(REQUIRED):
        print("YouTube upload skipped: OAuth secrets are not configured yet.")
        return 0
    if missing:
        raise RuntimeError("YouTube OAuth setup is incomplete. Missing: " + ", ".join(missing))

    video_path = OUT / ("wise_lab_shorts.mp4" if os.getenv("VIDEO_FORMAT", "landscape").lower() == "shorts"
                        else "wise_lab_video.mp4")
    if not video_path.is_file():
        raise RuntimeError(f"Finished video not found: {video_path}")

    title_file = OUT / "title.txt"
    title = title_file.read_text(encoding="utf-8").strip() if title_file.exists() else "WISE LAB"
    title = re.sub(r"\s+", " ", title).strip()[:100] or "WISE LAB"

    description_file = OUT / "description.txt"
    description = (
        description_file.read_text(encoding="utf-8").strip()
        if description_file.exists()
        else "Welcome to WISE LAB — thoughtful explainers about psychology and human behaviour.\n\n"
             "Educational content only; not medical advice.\n\n#WiseLab #Psychology #HumanBehaviour"
    )
    # YouTube rejects descriptions longer than 5,000 characters. Keep the
    # viewer-facing description concise while retaining per-asset references
    # in output/visual_manifest.json inside the review artifact.
    description = description.replace("\r\n", "\n").replace("\r", "\n")
    description = "".join(
        char for char in description
        if char in "\n\t" or ord(char) >= 32
    )
    description_lines = description.splitlines()
    pixabay_lines = [
        line for line in description_lines
        if line.strip().lower().startswith("pixabay media:")
    ]
    if pixabay_lines:
        description_lines = [
            line for line in description_lines
            if not line.strip().lower().startswith("pixabay media:")
        ]
        description_lines.extend([
            "",
            f"Visual media: Pixabay ({len(pixabay_lines)} assets).",
            "Individual asset references are retained in the production visual manifest.",
        ])
    description = "\n".join(description_lines).strip()
    # The YouTube Data API enforces the description limit in UTF-8 bytes.
    # Reserve room for a clear notice if a long description needs shortening.
    shortened_notice = "\n[Description shortened to meet YouTube's 5,000-byte limit.]"
    if len(description.encode("utf-8")) > YOUTUBE_DESCRIPTION_MAX_BYTES:
        budget = YOUTUBE_DESCRIPTION_MAX_BYTES - len(shortened_notice.encode("utf-8"))
        description = truncate_utf8(description, budget) + shortened_notice
    description_bytes = len(description.encode("utf-8"))
    if description_bytes > YOUTUBE_DESCRIPTION_MAX_BYTES:
        raise RuntimeError(
            f"YouTube description is {description_bytes} bytes; maximum is "
            f"{YOUTUBE_DESCRIPTION_MAX_BYTES}. Upload stopped before sending the video."
        )
    hashtag_count = validate_hashtags(title, description)
    print(
        f"YouTube description validated: {description_bytes}/"
        f"{YOUTUBE_DESCRIPTION_MAX_BYTES} UTF-8 bytes."
    )
    print(f"YouTube hashtags validated: {hashtag_count}/{YOUTUBE_HASHTAG_MAX}.")
    tags = ["WISE LAB", "psychology", "human behaviour", "human behavior",
            "psychology explained", "self awareness", "mental strength",
            "personal growth", "emotional intelligence"]
    privacy = os.getenv("YOUTUBE_PRIVACY_STATUS", "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        raise RuntimeError("YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public.")
    if privacy != "private":
        raise RuntimeError("Automatic publishing is locked to private for the initial rollout.")

    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False,
    )

    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"YouTube upload progress: {int(status.progress() * 100)}%")
        except HttpError as error:
            if error.resp.status not in (500, 502, 503, 504) or retries >= 5:
                raise
            retries += 1
            delay = min(2 ** retries, 60)
            print(f"Temporary YouTube upload error; retry {retries}/5 in {delay}s.")
            time.sleep(delay)

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube API returned success without a video ID.")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    (OUT / "youtube_video_url.txt").write_text(video_url + "\n", encoding="utf-8")
    review_checklist = OUT / "review_checklist.md"
    if review_checklist.is_file():
        with review_checklist.open("a", encoding="utf-8") as checklist:
            checklist.write("\n## Private YouTube review link\n\n")
            checklist.write(video_url + "\n")
            checklist.write("\nThe video remains Private. Publish manually only after completing the checklist.\n")
    thumbnail_path = OUT / "wise_lab_thumbnail.jpg"
    if os.getenv("VIDEO_FORMAT", "landscape").lower() != "shorts" and thumbnail_path.is_file():
        try:
            thumbnail_media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg", resumable=False)
            youtube.thumbnails().set(videoId=video_id, media_body=thumbnail_media).execute()
            print("Custom WISE LAB thumbnail uploaded.")
        except Exception as thumbnail_error:
            # Keep the successfully uploaded video even if YouTube rejects its thumbnail.
            print(f"THUMBNAIL_UPLOAD_WARNING: {thumbnail_error}")

    print("YOUTUBE_UPLOAD_SUCCESS")
    print(f"Video URL: https://www.youtube.com/watch?v={video_id}")
    print("Privacy: PRIVATE (review in YouTube Studio before publishing).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"YOUTUBE_UPLOAD_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
