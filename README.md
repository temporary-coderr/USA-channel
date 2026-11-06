# WISE LAB — Automated psychology video production

WISE LAB is designed as a small editorial studio: the human controls the script and research; the production pipeline handles repetitive video work. Every finished episode remains private until the channel owner approves it.

## The production loop

1. The channel owner supplies and approves `scripts/script.txt`.
2. The matching research ledger is supplied in `scripts/research_notes.md`, documenting every specific study, statistic, quotation, institution and empirical claim.
3. The pre-render editorial gate checks the script against recent episodes and flags claims for review.
4. GitHub Actions renders narration, visuals, captions, music, branding and thumbnail.
5. Technical QA checks the finished MP4 and creates a human review checklist.
6. The video is saved as a GitHub Actions artifact and, when YouTube OAuth is configured, uploaded as **Private**.
7. Review the private upload and artifact. Publish manually in YouTube Studio only after approval.

**There is no automatic script writing, script replacement, or public publishing.** The daily script-writing task has been paused. A passing technical check is not a fact-check, a creative-quality guarantee, or a YouTube Partner Program approval guarantee.

## Script submission — human-controlled

Do not use a scheduled bot to invent, replace, or commit the channel's scripts. Prepare the script first, fact-check it, and approve it yourself.

Before starting a render, update both files together:

- `scripts/script.txt` — final, narration-ready English script.
- `scripts/research_notes.md` — source ledger for the claims in that exact script.

The source ledger must list the short claim paraphrase, original source title, author/organization, publication date, direct URL, studied population/method, limitations, and whether the narration describes correlation or causation. If the script makes no specific empirical claims, say so explicitly. Never invent sources or rely on search snippets alone.

Only after you approve both files, commit/push them to `main`. The GitHub Actions workflow watches `scripts/script.txt`; a successful commit to that path starts a landscape render automatically.

For a manual render without changing the script:
1. Open **Actions → Build WISE LAB video from script → Run workflow**.
2. Choose `landscape` for 16:9 long-form or `shorts` for 9:16.
3. Wait for the workflow and inspect its artifact and private YouTube upload.

## Editorial safeguards

- `editorial_gate.py` compares the episode body with up to 20 previous versions in Git history, excluding recurring channel packaging. It stops a near-duplicate at 84% similarity or higher.
- The gate flags statistics, studies, research language, named institutions, dates, quotations and sweeping/causal wording for source review.
- `scripts/research_notes.md` is the source ledger paired with the episode.
- Automated flags do not browse or fact-check claims. Open each cited source and verify the actual population, method, wording and limitations yourself.

## Production settings

- **Narration:** Microsoft Edge-TTS, `en-US-AndrewNeural`, rate `+5%`. This setting is intentionally kept unchanged.
- **Long-form:** 1920×1080, 30 fps, 5-second WISE LAB intro and 7-second branded outro.
- **Shorts:** 1080×1920, 30 fps, no intro or outro; the renderer rejects scripts longer than 400 words.
- **Audience direction:** English-language psychology and human-behaviour explainers for a primarily US audience. Use natural US English and US-relevant everyday settings/examples when the script calls for them; do not force US references into universal topics.
- **Visuals:** Pixabay first, optional Pexels fallback, Openverse still-image fallback, and up to six selective OpenAI-generated stills when `OPENAI_API_KEY` is configured. Every episode should use topic-specific visual storytelling, original diagrams/graphics where they genuinely explain an idea, and varied male character poses. The approved male Edge-TTS voice remains unchanged.
- **Editing:** narration-specific visual cuts targeted around every three seconds, restrained motion, colour treatment and short cross-dissolves.
- **Captions:** burned-in phrase captions plus SRT/ASS sidecars. Timing is estimated from narration segment duration; it is not word-level speech recognition.
- **Music:** rotating Openverse tracks filtered for CC0/CC BY and commercial-use/modification permissions when a suitable unused track is available. If no suitable track is found, the video renders without BGM rather than using the old synthetic bed.
- **Asset history:** provider IDs and SHA-256 fingerprints are recorded. New assets also receive perceptual difference-hash fingerprints (three sampled frames for video) to reject many resized/re-encoded or near-identical visuals. This is a practical similarity guard, not perfect visual understanding; old history entries without perceptual hashes remain protected by provider IDs and exact hashes.
- **Visual freshness:** the renderer fails closed when it detects a near-duplicate rather than silently recycling it. A failed visual check may require a fresh render/search result; do not delete history to bypass the guard.
- **Upload:** YouTube privacy is locked to **Private** in `upload_youtube.py`. Public publishing must be done manually by the channel owner.

## Technical QA and review pack

After rendering, `quality_check.py` verifies:
- Expected resolution and approximately 30 fps.
- Presence of video and audio streams and plausible MP4 size/duration.
- Caption sidecar structure.
- That the scene plan preserves the original narration word sequence.
- Visual manifest completeness, fingerprints and duplicate hashes.
- Presence of the source ledger.

It writes:
- `output/technical_quality.txt`
- `output/technical_quality.json`
- `output/review_checklist.md`

A hard technical failure stops the private-upload step. Warnings require human attention. These checks cannot judge whether a story is insightful, whether a stock shot truly fits its line, whether a source supports a claim, or whether music sounds right on real speakers.

### Human approval checklist

Before publishing, watch the full video and:
- Listen on headphones and phone speakers; confirm the voice stays clear above BGM.
- Check every shot for relevance, repetition, awkward expressions and misleading implications.
- Check caption wording, timing, readability and safe margins.
- Check for black/frozen frames, abrupt cuts, pacing problems and audio glitches.
- Verify every research claim against its original source.
- Check visual and music attribution/licence conditions.
- Confirm the title, thumbnail and description are accurate and not clickbait.
- Confirm the episode adds original explanation, examples and practical value.

If anything is uncertain, keep the video private and fix it first.

## GitHub Actions secrets

Add these in **Settings → Secrets and variables → Actions**. Never paste secret values into chat or commit them to the repository.

| Secret | Purpose |
| --- | --- |
| `PIXABAY_API_KEY` | Required stock-media search key |
| `OPENAI_API_KEY` | Optional selective GPT Image still generation; API billing may apply |
| `GROQ_API_KEY` | Optional image-prompt refinement only |
| `PEXELS_API_KEY` | Optional stock-media fallback |
| `YOUTUBE_CLIENT_ID` | Google OAuth Desktop app client ID |
| `YOUTUBE_CLIENT_SECRET` | Google OAuth Desktop app client secret |
| `YOUTUBE_REFRESH_TOKEN` | Google OAuth refresh token |

All three YouTube OAuth secrets are needed for private upload. If all three are absent, rendering can still finish and upload is skipped. A partial OAuth setup causes upload to fail after the artifact is saved.

## One-time YouTube authorization (Windows)

1. In Google Cloud Console, enable **YouTube Data API v3**.
2. Create an OAuth client ID of type **Desktop app** and download its JSON.
3. Save it beside `authorize_youtube.py` as `client_secret.json`.
4. If the consent screen is in Testing mode, add the channel owner's Google account as a test user. Refresh tokens for external apps in Testing can expire after seven days.
5. From the repository folder in PowerShell, run:

   ```powershell
   py -m pip install -r requirements.txt
   py authorize_youtube.py
   ```

6. Sign in with the Google account that owns the target channel and approve upload access.
7. Add the three printed values as GitHub Actions secrets. Keep OAuth files private; never commit or share them.

## Important operating notes

- Script input: `scripts/script.txt`; paired evidence ledger: `scripts/research_notes.md`.
- FFmpeg runs on GitHub-hosted Ubuntu; your Windows PC does not need to stay on.
- `PIXABAY_API_KEY` is required by the current render pipeline.
- OpenAI image generation is optional and may incur API charges separate from ChatGPT.
- Workflow artifacts are retained for seven days.
- The voice is generated by Edge-TTS. YouTube monetization eligibility and Microsoft's service/licensing terms are separate questions; verify commercial-use rights for the voice service before scaling.
- No automated system can guarantee YPP approval. Originality, meaningful human value, accurate research and non-repetitive presentation remain essential.
