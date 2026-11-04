# USA-channel — Script-to-video editor

This repository can turn a supplied English script into a silent, edited YouTube video. The new workflow runs on GitHub-hosted Ubuntu runners; your Windows PC does not need to stay on.

## New workflow: build video from your script

1. Replace the sample text in `scripts/script.txt` with your full script and commit it.
2. Open **Actions → Build silent video from script → Run workflow**.
3. Choose **landscape** for normal YouTube (16:9, 1080p) or **shorts** (9:16).
4. When the run completes, open its summary and download the `usa-channel-video-...` artifact.
5. Add your recorded voice to the MP4 in your video editor, adjust narration/caption timing if needed, then upload to YouTube.

## What the renderer does

- Uses Groq to split the supplied script into ordered scenes and create visual search phrases. It is instructed to preserve the script's narration wording.
- Searches Pixabay for scene-matched stock video clips. If no suitable video is returned, it falls back to a relevant still image.
- Adds a slow Ken Burns zoom to still-image scenes, light color treatment and fade-ins.
- Burns readable phrase-sized captions into the video and also exports a separate `captions.srt`.
- Exports a silent MP4 and the original script/scene plan for review.

The current renderer concatenates scenes with clean cuts; it does not yet create complex cross-dissolves, animated word-by-word karaoke captions, AI-generated imagery, or exact voice-aligned captions. Scene timing is estimated from word count at 140 words/minute. After recording your voice, adjust timing in your editor if needed. Stock footage is illustrative B-roll, not proof that an event happened.

## Required repository secrets

Add these in **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Script-to-scene planning |
| `PIXABAY_API_KEY` | Stock video and image search |

Do not paste secrets into chat, scripts, workflow files, or commits. Do not use paid AI-image services unless you separately choose to enable them and understand their pricing. This workflow does not require a voice-cloning or TTS service.

## Notes

- The script should be in English and preferably at least 100 words.
- GitHub-hosted Actions usage is subject to your GitHub plan's included minutes and limits.
- Pixabay search results and availability vary. Review each downloaded asset and the current license/terms before publishing.
- Groq scene planning and search results can be imperfect. Review the output before publication.
- No narration, voice cloning, YouTube upload, or automatic thumbnail generation is included in this workflow. The MP4 is silent so you can add your own voice recording.
- Outputs are uploaded as a GitHub Actions artifact and retained for 7 days.
