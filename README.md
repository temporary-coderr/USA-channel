# WISE LAB — Script-to-video automation

Upload your English psychology script to `scripts/script.txt`, then run the GitHub Actions workflow. The pipeline creates the narration, finds stock visuals, edits the video, adds captions and WISE LAB branding, creates a thumbnail, and uploads the finished video as **Private** when YouTube OAuth secrets are configured.

## Daily workflow

1. Replace the contents of `scripts/script.txt` with your new script and commit the change.
2. Open **Actions → Build WISE LAB video from script → Run workflow**.
3. Choose `landscape` for a normal 16:9 video or `shorts` for a 9:16 Short.
4. Wait for the workflow to finish. The MP4, captions, thumbnail, title and visual manifest are saved as a downloadable artifact.
5. If YouTube OAuth is configured, the MP4 is uploaded automatically as **Private**. Review it in YouTube Studio before publishing.

## What runs automatically

- Uses the same Edge-TTS fallback voice as the working `bot.py`: `en-US-AndrewNeural`, at `+5%` speaking rate.
- Creates the scene plan locally from the script; the existing Edge-TTS narration remains unchanged.
- When `GEMINI_API_KEY` is configured, generates six selective 1K custom psychology images with Gemini 3.1 Flash Image, evenly distributed through the video (configurable from 5–7). These supplement—not replace—Pixabay, Pexels and Openverse stock footage/images.
- When `GROQ_API_KEY` is configured, Groq GPT-OSS 20B refines the prompts for those AI stills; if Groq is unavailable, local prompts are used. Groq does not generate the images.
- If Gemini is unavailable or generation fails, that shot automatically falls back to the normal stock-media search. AI image generation is optional and can incur Gemini API charges.
- Cuts to a new, narration-specific visual approximately every 3 seconds while keeping the voiceover continuous; short cross-dissolves soften the cuts.
- Alternates Pixabay and optional Pexels as the first stock-video search provider so one library does not dominate every shot.
- Uses Pixabay and Pexels for stock video; if no suitable video is found, it tries their photo libraries and then Openverse for large CC0/CC BY still images with commercial-use/modification filters.
- Pexels is optional. Keep `PEXELS_API_KEY` only if you already have an approved key; the bot continues with Pixabay and Openverse if it is absent.
- Avoids reusing previously selected asset IDs across providers using `visual_history/used_assets.json`; Pexels and Openverse IDs are provider-prefixed.
- Stores SHA-256 fingerprints for downloaded visuals and stops rather than reusing an exact byte-for-byte duplicate; this does not detect visually similar edits or crops.
- Adds provider/creator visual credits and Openverse licence/source details to the generated YouTube description where metadata is available.
- Prefers stock video renditions near the target output resolution instead of unnecessarily downloading the largest available file for every short shot.
- Saves `description.txt` and `editorial_review.txt` in the downloadable workflow artifact.
- Adds gentle motion to still images, subtle camera movement to stock clips, colour treatment and cross-dissolves.
- Creates phrase-sized burned-in captions and a separate `output/captions.srt`. Caption timing is estimated from each narration segment's duration; it is not word-level speech recognition.
- For landscape videos, adds the 5-second WISE LAB intro and 7-second outro, including the animated subscribe end card.
- Shorts skip the intro and outro.
- Creates `output/wise_lab_thumbnail.jpg`; for landscape uploads, it also attempts to set that image as the YouTube thumbnail.
- Upload privacy is locked to **Private**.

## Required GitHub Actions secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
| --- | --- |
| `PIXABAY_API_KEY` | Required: primary stock video and image search |
| `GEMINI_API_KEY` | Optional: generates 5–7 custom psychology still images per video; paid API usage may apply |
| `GROQ_API_KEY` | Optional: refines prompts for Gemini-generated images; Groq does not generate images |
| `PEXELS_API_KEY` | Optional: fallback stock video and image search (only if you already have an approved key) |
| `YOUTUBE_CLIENT_ID` | Google OAuth Desktop app client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth Desktop app client secret |
| `YOUTUBE_REFRESH_TOKEN` | Google OAuth refresh token |

The three YouTube secrets are only needed for automatic upload. If they are all absent, the workflow still renders the video and skips upload. If only some are configured, upload fails with an incomplete OAuth setup error.

## One-time YouTube authorization (Windows)

**Never send OAuth credentials or tokens in chat, and never commit them to GitHub.**

1. Open Google Cloud Console, create/select a project, and enable **YouTube Data API v3**.
2. Create an OAuth client ID of type **Desktop app** and download its JSON file.
3. Save the downloaded file beside `authorize_youtube.py` as `client_secret.json`.
4. If the OAuth consent screen is in Testing mode, add the Google account that owns the target YouTube channel as a test user. Refresh tokens issued to external apps in Testing can expire after 7 days.
5. In PowerShell, from the repository folder, run:

   ```powershell
   py -m pip install -r requirements.txt
   py authorize_youtube.py
   ```

6. Sign in with the Google account that owns the target channel and approve YouTube upload access.
7. Add the printed client ID, client secret and refresh token as the three GitHub Actions secrets above. Keep local OAuth files private and delete them after safely storing the secrets.

## Notes

- Script input path: `scripts/script.txt`.
- Voice: `en-US-AndrewNeural`; change the workflow's `EDGE_TTS_VOICE` only if you intentionally want another voice.
- FFmpeg runs on GitHub-hosted Ubuntu; your Windows PC does not need to stay on.
- The workflow requires the Pixabay secret even if the YouTube upload secrets are not configured.
- Gemini and Groq are optional; without Gemini, the workflow uses the existing stock-only visual pipeline. Keep an eye on Google AI Studio usage and billing.
- Review narration, stock footage, captions, claims and licensing before making a video public.
- Workflow artifacts are retained for 7 days.
