# WISE LAB — Script-to-video editor

This repository turns an English psychology script into a documentary-style video with consistent WISE LAB branding. The workflow runs on GitHub-hosted Ubuntu; your Windows PC does not need to stay on.

## Build a WISE LAB video

1. Replace the sample text in `scripts/script.txt` with your complete script and commit it.
2. Open **Actions → Build WISE LAB video from script → Run workflow**.
3. Choose **landscape** for a normal YouTube video (16:9, 1080p) or **shorts** (9:16).
4. Download the `wise-lab-video-...` artifact when the run completes.
5. Download the finished video and review the narration, captions, and selected visuals before publishing.

## What the renderer does

- Uses Gemini Flash as the primary scene planner and automatically falls back to Groq if Gemini is unavailable or returns an invalid plan. Both planners preserve the supplied narration wording.
- Searches Pixabay for relevant stock video and falls back to still photos when needed.
- Adds gentle movement to still images, light colour treatment and fades.
- Burns phrase-sized captions into the video and exports a separate `captions.srt`.
- For **landscape long videos only**, adds a custom WISE LAB vector W mark, a 5-second intro, a 7-second outro, and original synthesized ambient welcome music.
- The long-video intro says **“Explore the Mind. Understand Human Behaviour.”** and the outro says **“Keep Thinking. Stay Curious. Subscribe to WISE LAB.”**
- **Shorts skip the intro, outro, and branding music** so they begin immediately. The Inworld-generated narration is included in both formats.

## Required repository secrets

Add these in **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Primary script-to-scene planning (Gemini Flash) |
| `GROQ_API_KEY` | Automatic fallback scene planner if Gemini fails |
| `PIXABAY_API_KEY` | Stock video and image search |
| `INWORLD_API_KEY` | Inworld text-to-speech narration |

Gemini uses the `gemini-3.8-flash` model by default. Do not paste secrets into chat, scripts, workflow files, or commits. The existing Pixabay media search, Inworld narration, captions, and video-rendering steps remain unchanged.

## Important limitations

- Scene durations and caption timing are estimated from word count at 140 words/minute. Long-video captions start after the 5-second intro; Shorts captions start at the beginning. Both may need adjustment to match your recorded voice.
- The current renderer uses clean cuts between stock scenes; it does not yet provide complex cross-dissolves, exact voice-aligned captions, or AI-generated images.
- Pixabay results and availability vary. Review footage and applicable license terms before publishing.
- No narration, YouTube upload, or automatic thumbnail generation is included.
- GitHub-hosted Actions usage is subject to your GitHub plan's included minutes and limits. Output artifacts are retained for 7 days.
