from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_FILE = Path("client_secret.json")
TOKEN_FILE = Path("youtube_token.json")


def main() -> None:
    if not CLIENT_FILE.is_file():
        raise SystemExit(
            "Missing client_secret.json. Download the OAuth Desktop app JSON "
            "from Google Cloud Console and place it beside this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        authorization_prompt_message="Open this URL in your browser: {url}",
        success_message="WISE LAB has been authorized. You can close this browser tab.",
        access_type="offline",
        prompt="consent",
    )
    if not credentials.refresh_token:
        raise SystemExit(
            "Google did not return a refresh token. Revoke the app's access in your "
            "Google Account, then run this script again and approve access."
        )

    data = json.loads(credentials.to_json())
    TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("\nAuthorization successful.")
    print("A local youtube_token.json file was created. Do NOT commit or share it.")
    print("\nCopy these three values into GitHub repository Actions secrets:")
    print("\nYOUTUBE_CLIENT_ID=" + str(data.get("client_id", "")))
    print("YOUTUBE_CLIENT_SECRET=" + str(data.get("client_secret", "")))
    print("YOUTUBE_REFRESH_TOKEN=" + str(data.get("refresh_token", "")))


if __name__ == "__main__":
    main()
