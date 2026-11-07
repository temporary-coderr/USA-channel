# WISE-LAB Procedural SVG Animation Engine

## Current prototype

The engine turns narration into ordered visual beats, creates original SVG compositions, animates them frame-by-frame, and encodes a review MP4. It uses Python, CairoSVG, Pillow, FFmpeg, and standard-library audio synthesis. It does not call Pixabay, Openverse, OpenAI Images, Gemini Images, or another external image service.

### Animation features

- Character breathing/bobbing and gesture movement.
- Per-scene camera push-in and alternating pan.
- Subtle background parallax.
- Short crossfade transitions between beats.
- A new script-directed SVG composition for each beat.
- Original generated sound effects: a short WISE-LAB sonic mark, soft UI clicks/ticks, steps, impacts, and transition whooshes.
- Sound events are timed to beat boundaries and selected actions; effects are deliberately restrained rather than playing on every word.

## Render a review video

Use GitHub Actions → **WISE LAB SVG visual prototype** → Run workflow. Choose landscape or Shorts. The workflow is manual-only, runs tests, renders the complete current script, and creates one review artifact with:

- `wise_lab_animated_preview.mp4` — animated visual preview with synthesized SFX.
- `sound_effects.wav` — separate generated effects track.
- `animation_manifest.json` — timing, beats, effects, and render metadata.
- `scene_svgs/` — editable vector source for each visual beat.

Or run locally:

```bash
python -m pip install CairoSVG Pillow
python -m unittest discover -s tests -v
python svg_video_renderer.py --script scripts/script.txt --output output/svg_animation_preview --format landscape --wpm 140 --seconds 3 --fps 12 --width 720
```

Use `--format shorts` for vertical 9:16 output. The preview defaults to 720 pixels wide and 12 FPS to keep the first review render practical. The final production pipeline can raise resolution and frame rate after timing and visual quality are approved.

## Production integration status

This remains a separate review renderer. It does not yet replace `render_script.py`, attach the existing Edge-TTS narration, mix the channel's background music, or upload to YouTube. The SFX track is generated separately and then muxed into the preview. Keep the current production workflow unchanged until the visual output, audio balance, long-form runtime, and resource usage have been reviewed.

The visual vocabulary is deliberately extensible. If a script introduces an unsupported subject, add a specific SVG character, prop, environment, or diagram. Do not substitute unrelated stock media.
