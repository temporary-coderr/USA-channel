# WISE-LAB Procedural SVG Visual Engine

## What it does

`svg_animation_engine.py` turns the current narration script into an ordered set of original SVG illustrations and PNG previews. It uses Python, procedural vector drawing, and CairoSVG. It does not call Pixabay, Openverse, OpenAI Images, Gemini Images, or another external image service.

The scene plan preserves every script word in order and aims for a visual beat about every three seconds at the configured narration speed. Each beat is analysed for a likely subject and action, then composed from vector characters, props, diagrams, backgrounds, labels, and channel styling. A manifest records the narration span, duration, inferred subject/action, generated files, and image hash.

## Preview it

Use the separate **WISE LAB SVG visual prototype** workflow in GitHub Actions. It is manual-only and creates one review artifact containing the SVG source files, PNG previews, and manifest. It does not upload to YouTube and does not change the production renderer.

Or run locally:

```bash
python -m pip install CairoSVG
python svg_animation_engine.py --script scripts/script.txt --output output/svg_prototype --format landscape --wpm 140 --seconds 3
```

Choose `shorts` for vertical 1080×1920 output.

## Important limits of this first prototype

- It generates original, editable vector artwork, not photorealistic AI pictures.
- Its visual vocabulary is a growing set of reusable primitives. New subjects, props, gestures, environments, and diagram types can be added as the channel's scripts require them.
- It varies layout and composition deterministically from the narration and beat index; the prototype still needs editorial review for semantic accuracy and visual repetition.
- PNG previews are still illustrations. The production renderer must add timed movement, camera animation, transitions, and sound design before this becomes the final video engine.
- This prototype is intentionally separate from the production workflow. Do not remove the existing renderer's stock paths until the SVG output has been reviewed and the full video pipeline has passed short- and long-form tests.

The aim is to remove dependence on a finite stock library. It does not mean every possible subject is already modelled: missing visual concepts should be added as new SVG primitives, not filled with unrelated footage.
