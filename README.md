# USA-channel — YouTube Automation Lab

An experimental, script-first YouTube video pipeline for a psychology channel.

## First milestone

- Read narration from `script.txt`
- Generate MP3 narration through the local VoiceStudio HTTP API
- Download a relevant stock video from Pixabay
- Render an MP4 using FFmpeg
- Save output locally for review (no automatic upload)

## Important: VoiceStudio is local

The API endpoint `http://localhost:3900` is reachable only on the machine where VoiceStudio is running. A GitHub-hosted runner cannot access your Windows PC's localhost. Run the pipeline directly on your PC first, or configure a GitHub Actions **self-hosted Windows runner** on that PC.

## Setup (Windows 11)

1. Install Python 3.11+ and FFmpeg; ensure `ffmpeg` is on PATH.
2. Start VoiceStudio and verify its API is available at `http://localhost:3900`.
3. Open PowerShell in this repository.
4. Install dependencies: `py -m pip install -r requirements.txt`
5. Set your Pixabay key in the current PowerShell session:
   `$env:PIXABAY_API_KEY="YOUR_PIXABAY_KEY"`
6. Run: `py main.py`

Edit `script.txt` before each run. Generated files are saved in `output/`.

## Voice configuration

The current configuration uses model `omnivoice`, profile ID `f90360e8`, profile label `sndp`, and English. Change these in `main.py` if VoiceStudio settings change.

## Safety and publishing

This first version does not upload to YouTube. Review the rendered video, audio rights, footage license, and metadata before enabling any publishing workflow. Keep API keys out of source control and GitHub commits.
