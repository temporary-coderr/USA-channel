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
    (OUT / "youtube_video_url.txt").write_text(
        f"https://www.youtube.com/watch?v={video_id}\n", encoding="utf-8"
    )
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
