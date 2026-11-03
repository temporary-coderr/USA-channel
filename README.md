# USA-channel — Psychology Video Automation

This project generates an English-language psychology video using Groq for the script, Pixabay for scene-matched stock footage/images, VoiceStudio's existing `sndp` voice profile for narration, and FFmpeg for editing.

## What it generates

- A 5–7 minute documentary-style script (default target: 6 minutes)
- A title, description, tags and thumbnail search prompt in `output/metadata.json`
- Narration audio via VoiceStudio profile `sndp`
- Relevant Pixabay stock footage for each scene, with a photo fallback
- A 1080p landscape MP4 (or 1080x1920 Shorts when selected)
- SRT captions with phrase-sized caption chunks
- All outputs in a downloadable GitHub Actions artifact

The script prompt requires a strong opening, coherent storytelling, practical takeaways and cautious treatment of psychological claims. AI-generated scripts still need human review; this is not a guarantee of factual accuracy or professional editorial quality.

## Required GitHub Actions secrets

In **Settings → Secrets and variables → Actions → New repository secret**, add:

| Secret | Purpose |
|---|---|
| `GROQ_API_KEY` | Script generation |
| `PIXABAY_API_KEY` | Stock video and photo search |

Do not put keys in Python files or commit them.

Optional Actions variables (Settings → Secrets and variables → Actions → Variables):
- `VOICESTUDIO_API_URL` — defaults to `http://localhost:3900`
- `VOICESTUDIO_VOICE_ID` — defaults to `f90360e8`
- `VOICESTUDIO_VOICE_NAME` — defaults to `sndp`
- `VOICESTUDIO_MODEL` — defaults to `omnivoice`

## Important: this workflow requires your Windows PC

VoiceStudio is running on your PC, so a normal GitHub-hosted runner cannot connect to `localhost:3900`. The workflow is deliberately configured for a **self-hosted Windows x64 runner**. Install/register the GitHub Actions runner on the same PC as VoiceStudio, keep the runner service and VoiceStudio API running, and make sure FFmpeg is on PATH.

GitHub Actions will run daily at 18:30 India time (13:00 UTC), and can also be started manually from the Actions tab. Manual runs let you enter a topic and choose landscape or Shorts. A scheduled run defaults to landscape.

If you do not want your PC running, the voice step must be moved to a reachable hosted TTS provider or a secured remote VoiceStudio endpoint. Do not expose the local VoiceStudio API publicly without authentication and network protections.

## Run locally on Windows 11

1. Install Python 3.11+ and FFmpeg (including `ffprobe`), and add FFmpeg to PATH.
2. Start VoiceStudio and confirm its API is available at `http://localhost:3900`.
3. Open PowerShell in the repository and install packages:

   ```powershell
   py -m pip install -r requirements.txt
   ```

4. Set the API keys for this PowerShell session:

   ```powershell
   $env:GROQ_API_KEY="YOUR_GROQ_KEY"
   $env:PIXABAY_API_KEY="YOUR_PIXABAY_KEY"
   ```

5. Run:

   ```powershell
   py main.py
   ```

Optional settings:
- `VIDEO_TOPIC="..." ` — force a topic instead of automatic selection.
- `VIDEO_FORMAT=shorts` — vertical output.
- `TARGET_MINUTES=6` — target duration.

## Workflow

Open **Actions → USA Channel Video Automation → Run workflow**. For manual dispatch, optionally enter a topic and choose a format. Download the artifact named `usa-channel-output-...` after the run completes.

## Current limitations

- This generates videos and artifacts; it does **not** automatically publish to YouTube yet.
- Thumbnail artwork is not rendered yet; metadata includes a thumbnail search prompt.
- Scene durations and captions are estimated from narration word counts rather than forced-alignment transcription. Review timing before publishing.
- Pixabay assets are fetched at run time. Check the current Pixabay license/terms for each asset and retain any required attribution/records.
- Groq output and stock search results can be imperfect. Review every script, visual, caption and final video before publishing.
- A failed API call, missing secret, unavailable VoiceStudio, or missing FFmpeg stops the workflow with an error rather than silently producing an incomplete video.
