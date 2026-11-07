# WISE-LAB Procedural SVG Animation Engine

## Current prototype

The engine turns narration into ordered visual beats, creates original SVG compositions, animates them frame-by-frame, and encodes a review MP4. It uses Python, CairoSVG, Pillow, FFmpeg, and standard-library audio synthesis. It does not call Pixabay, Openverse, OpenAI Images, Gemini Images, or another external image service.

### Script-adaptive scene engine

The video renderer now uses `svg_scene_engine.py` as its visual composition layer. For every narration beat it derives a scene brief containing subject, action, emotion, environment, props, character variant, and composition. The flat-vector renderer draws the character and scene directly with SVG geometry. It includes expression-specific eyes, brows and mouths; walking/sitting/pointing/hiding/waving/thinking poses; blink and bob motion; multiple environments (rainy street, bedroom, park, workplace, interior and dark room); and script-selected props. Dog-focused beats place a dog alongside the character rather than showing an unrelated generic person. Layouts vary between beats.

The renderer uses `svg_story_planner.py` to send the complete narration-beat list to Groq once per video. Groq assigns a subject, action, emotion, environment, props, character variant, and composition to each beat; the renderer then draws those briefs using only original SVG geometry. Configure the repository secret `GROQ_API_KEY`; optionally set `GROQ_STORY_MODEL` to a supported Groq model. The workflow does not print or expose the key. If the key is absent, the API is unavailable, or a response contains unsupported values, the engine safely falls back to the deterministic local keyword planner. The AI planner cannot create new SVG assets: unsupported objects must still be added to the vector vocabulary. No stock images, raster assets, or external image-generation APIs are used.

### Animation features

- Character breathing/bobbing, blinking, expression changes and action-specific pose movement.
- Per-scene camera push-in and alternating pan.
- Subtle background parallax.
- Short crossfade transitions between beats.
- A new script-directed SVG composition for each beat.
- Original 1.5-second WISE-LAB sonic mark, soft UI clicks/ticks, steps, impacts, and selective transition accents.
- A continuous, locally synthesized ambient music bed with slow chord movement and no external/copyrighted recording.
- Effects are louder and clearer, but remain selective; transition whooshes are not played on every cut.
- A mastered preview mix is created separately from the isolated SFX track. Narration is not included in this prototype yet.

## Render a review video

Use GitHub Actions → **WISE LAB SVG visual prototype** → Run workflow. Choose landscape or Shorts. The workflow is manual-only, runs tests, renders the complete current script, and creates one review artifact with:

- `wise_lab_animated_preview.mp4` — animated visual preview with synthesized music and SFX.
- `audio_mix.wav` — mastered ambient music + SFX mix used in the MP4.
- `sound_effects.wav` — separate generated effects track.
- `animation_manifest.json` — timing, beats, effects, and render metadata.
- `scene_svgs/` — editable vector source for each visual beat.

Or run locally:

```bash
python -m pip install CairoSVG Pillow requests
python -m unittest discover -s tests -v
python svg_video_renderer.py --script scripts/script.txt --output output/svg_animation_preview --format landscape --wpm 140 --seconds 3 --fps 12 --width 720
```

Use `--format shorts` for vertical 9:16 output. The preview defaults to 720 pixels wide and 12 FPS to keep the first review render practical. The final production pipeline can raise resolution and frame rate after timing and visual quality are approved.

## Production integration status

This remains a separate review renderer. It does not yet replace `render_script.py`, attach the existing Edge-TTS narration, or upload to YouTube. The prototype uses an original synthesized ambient bed plus SFX; narration and final voice/music ducking will be added only when the prototype is ready for a separate integration test. Keep the current production workflow unchanged until the visual output, audio balance, long-form runtime, and resource usage have been reviewed.

The visual vocabulary is deliberately extensible. If a script introduces an unsupported subject, add a specific SVG character, prop, environment, or diagram. Do not substitute unrelated stock media.
