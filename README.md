# WISE LAB — Script-to-video editor

This repository turns an English psychology script into a documentary-style video with consistent WISE LAB branding. The workflow runs on GitHub-hosted Ubuntu; your Windows PC does not need to stay on.

## Build and upload a WISE LAB video

1. Replace the sample text in `scripts/script.txt` with your complete script and commit it.
2. Open **Actions → Build WISE LAB video from script → Run workflow**.
3. Choose **landscape** for a normal YouTube video (16:9, 1080p) or **shorts** (9:16).
4. The workflow renders the video and, when YouTube OAuth secrets are configured, uploads it to your channel as **Private**.
5. Review the uploaded video in YouTube Studio before changing its visibility.

## What the renderer does

- Uses Gemini Flash as the primary scene planner and automatically falls back to Groq if Gemini is unavailable or returns an invalid plan.
- Searches Pixabay for relevant stock video and falls back to still photos when needed.
- Adds gentle movement to still images, light colour treatment and fades.
- Burns phrase-sized captions into the video and exports a separate `captions.srt`.
- For **landscape long videos only**, adds a custom WISE LAB vector W mark, a 5-second intro, a 7-second outro, and original synthesized ambient welcome music.
- **Shorts skip the intro, outro, and branding music** so they begin immediately. Inworld narration is included in both formats.
- Uploads the final MP4 with its title and basic WISE LAB description/tags through the YouTube Data API. Upload privacy is locked to **private**.

## Required repository secrets

Add these in **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Primary script-to-scene planning (Gemini Flash) |
| `GROQ_API_KEY` | Automatic fallback scene planner |
| `PIXABAY_API_KEY` | Stock video and image search |
| `INWORLD_API_KEY` | Inworld text-to-speech narration |
| `YOUTUBE_CLIENT_ID` | Google OAuth Desktop app client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth Desktop app client secret |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived OAuth refresh token for your YouTube account |

## One-time YouTube authorization (Windows)

**Do not send OAuth credentials or tokens in chat, and never commit them to GitHub.**

1. Open [Google Cloud Console](https://console.cloud.google.com/), create/select a project, enable **YouTube Data API v3**, and configure the OAuth consent screen.
2. Create an OAuth client ID of type **Desktop app**. Download its JSON file and save it beside `authorize_youtube.py` as `client_secret.json`.
3. If the OAuth consent screen is in **Testing** mode, add the Google account that owns your WISE LAB YouTube channel as a test user. Note: external apps left in Testing can receive refresh tokens that expire after 7 days; move the consent configuration to an appropriate production status if you need unattended uploads to continue beyond that. Google may require verification depending on the app and scopes.
4. On your Windows PC, open PowerShell in the repository folder and run:

   ```powershell
   py -m pip install -r requirements.txt
   py authorize_youtube.py
   ```

5. A browser opens. Sign in with the Google account that owns the target YouTube channel and approve the YouTube upload permission.
6. The script prints the three OAuth values. Add them as the three GitHub Actions secrets listed above. The local `youtube_token.json` file is sensitive; keep it private and delete it after the secrets are saved.
7. Run the workflow again. The upload step will print the YouTube video URL. If OAuth secrets are not configured yet, rendering still succeeds and upload is skipped.

The authorization uses only the `youtube.upload` scope. Google access tokens are refreshed automatically during each upload. The refresh token can still be revoked or expire, so reconnect if GitHub Actions reports an OAuth `invalid_grant`.

## Security files

- `client_secret.json` and `youtube_token.json` are local-only OAuth files and must never be committed.
- GitHub Actions secrets are masked by GitHub and are not written into the repository.
- The workflow currently forces uploads to **Private**. There is no automatic public publishing.

## Important limitations

- Scene durations and caption timing are estimated from word count at 140 words/minute and may need adjustment.
- Pixabay results and availability vary. Review footage and applicable license terms before publishing.
- YouTube API upload quota and channel/account restrictions still apply.
- Output artifacts are retained for 7 days.
