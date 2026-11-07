# WISE-LAB Animation-First Video Engine

## Status

Approved production direction. This document records the requirements for the next renderer implementation. It does **not** mean the SVG animation engine has already been implemented.

## Product goal

Replace stock-footage-led editing with original, script-specific 2D animated psychology explainers. The system must be able to produce Shorts and long-form landscape videos of at least 15 minutes, with no arbitrary 8- or 10-minute ceiling using locally generated SVG artwork, procedural animation, narration, captions, music, and FFmpeg.

The intended production path should remain compatible with the existing GitHub Actions workflow and its manual-only trigger. Do not reintroduce automatic rendering on push.

## Non-negotiable visual rules

1. **No stock footage or stock-image fallback.** Do not use Pixabay, Openverse, or other stock media as scene fillers.
2. **Every video gets its own visual plan.** Generate scene descriptions and compositions from the current script, not from a fixed sequence of reusable scenes.
3. **New composition for each scene.** A scene may reuse approved character parts, but its arrangement, action, environment, props, camera framing, and visual explanation must fit the current narration.
4. **Reuse identity, not finished scenes.** Recurring WISE-LAB human/animal characters and their underlying vector components may be reused. Do not automatically recycle a complete prior scene, storyboard panel, or scene-specific SVG.
5. **Script relevance is mandatory.** Every scene must visibly represent the narration it accompanies. If a suitable scene cannot be generated, flag/fail that scene for review rather than inserting unrelated visuals.
6. **No visual gaps.** Every narration interval must have an intentional visual: character action, environment, prop, diagram, kinetic typography, or a meaningful combination.
7. **No black/empty frames.** Validate rendered frame coverage and detect accidental blank/black intervals.
8. **Avoid template repetition.** Reusable animation primitives are allowed, but do not use the same scene sequence, composition, or character action pattern across unrelated videos.

## Visual timing and format

- Target an average visual change about every 3 seconds, adjusted to narration and story beats rather than enforced mechanically.
- Hold information-dense diagrams for approximately 5–7 seconds when needed for readability.
- Support videos of 6–8 minutes, 10 minutes, 15 minutes, and longer, as well as Shorts. There must be no hard-coded maximum duration of 8 or 10 minutes; practical limits should come from available runner time, memory, storage, and rendering resources.
- At a 3-second average visual rhythm, a 15-minute video may contain roughly 300 visual beats. The planner, manifest, uniqueness checks, and renderer must handle long scene lists without truncating the script or silently reducing visual quality.
- Design rendering to process scenes in manageable chunks where useful, while preserving continuous narration timing, audio/video synchronization, transitions, and a single final output. Clean up temporary frame files safely to control disk usage.
- Preserve 1080p output and the existing format selection (landscape or Shorts).
- Keep narration synchronized with animation, captions, transitions, and music.
- Do not change the user's selected format automatically.

## SVG asset and scene architecture

Build modular vector assets that can be assembled into new scene compositions:

- Human characters: reusable identity, body parts, clothing variants, poses, facial expressions, and gestures.
- Animals: species-specific silhouettes, body parts, facial expressions, and a practical set of poses/actions (for example dog walking, sitting, running, looking, and tail wagging).
- Environments: rooms, homes, workplaces, streets, parks, classrooms, and other script-relevant locations.
- Objects and props: everyday items and psychology-specific objects.
- Diagrams: topic-specific processes, relationships, brain/memory/attention concepts, timelines, cycles, comparisons, and labels.
- Motion graphics: typography, highlights, arrows, callouts, transitions, and camera movement.

Use SVG groups/layers so parts can be translated, rotated, scaled, replaced, and animated independently. Prefer code-generated SVG and deterministic animation primitives so rendering does not depend on paid image/video generation APIs.

## Reuse policy

| Asset | Policy |
| --- | --- |
| Character identity and base vector components | Reusable |
| Character poses and expressions | Reusable building blocks; select based on the current scene |
| Animal identity and base vector components | Reusable |
| Props and environment components | Reusable building blocks |
| Complete scene compositions | Do not automatically reuse between videos |
| Topic-specific diagrams | Create for the current script/concept; reuse only when genuinely identical and appropriate |
| Scene order/storyboard | Generate from each video's script; never use a fixed template |

Reusing the same character is encouraged for channel identity. The character must perform actions and interact with objects/environments that make sense for the current script. Do not force the recurring character into a scene when another visual would explain the narration better.

## Script-to-scene planning

For each video:

1. Read the complete script and identify its main topic, supporting concepts, examples, entities, emotional beats, and claims.
2. Break narration into meaningful visual beats, targeting roughly 3 seconds each where practical.
3. For every beat, specify the exact narration span, visual purpose, subjects, action, environment, props, composition, camera movement, animation, and expected duration.
4. Choose or assemble appropriate SVG components, then create a new scene composition tailored to that beat.
5. Ensure animals, people, objects, and diagrams are included only when relevant to the script.
6. Check that the scene communicates the intended idea without relying only on a generic decorative character.
7. Generate a per-video visual manifest recording scene IDs, descriptions, asset provenance, and visual fingerprints.

The scene planner must prioritize semantic relevance over filling a scene quickly. It must not broaden a query or substitute a loosely related metaphor when the narration calls for a specific subject.

## Visual uniqueness and history

Maintain a per-video and channel-level visual history.

- Record normalized scene descriptions and perceptual fingerprints for rendered scenes.
- Compare new scene compositions against prior videos to identify duplicate or near-duplicate complete scenes.
- Reuse of a character or a low-level SVG component must not by itself trigger a duplicate rejection.
- Flag repeated scene composition, action, environment, prop arrangement, and camera framing.
- Permit reuse only when the scene is genuinely appropriate and the reuse is intentional; do not use history as a reason to insert unrelated visuals.
- Keep the visual manifest and review report in the render artifact.

## Technical implementation direction

- Python: script analysis, scene planning, SVG generation, asset assembly, timing, and validation.
- SVG: scalable vector artwork and layered character/scene components.
- Animation: code-driven transforms, opacity, path motion, and timed scene transitions.
- FFmpeg: combine rendered animation, Edge-TTS narration, captions, music, and final video encoding.
- Keep the implementation compatible with the current free GitHub-hosted runner where practical. Avoid paid per-scene AI image/video APIs as a required dependency.
- Keep the current Edge-TTS voice and manual workflow behavior unless separately approved.

## Quality gates before a video is accepted

A render should be rejected or flagged for review if:

- Any scene is missing, blank, or visually unrelated to its narration.
- A stock asset is used.
- The same complete scene is recycled from an earlier video without an explicit, relevant reason.
- A scene has no meaningful visual action or explanatory purpose.
- Captions or diagram labels are unreadable or obscured.
- Diagram timing is too short to read.
- The video contains black frames, broken transitions, or audio/video synchronization errors.
- The visual manifest is missing or uniqueness checks cannot be completed.

Automated checks support editorial review; they do not replace human review or fact-checking.

## Implementation plan

1. Build a small original SVG character prototype and test independent body-part animation.
2. Add a small library of human, animal, object, environment, and diagram primitives.
3. Implement a scene planner that converts a script into timed, script-specific visual beats.
4. Implement SVG scene composition and animation rendering.
5. Produce a 60-second prototype Short and review relevance, movement, readability, and visual quality.
6. Expand to a 3-minute test, then 6–8 minutes, 10 minutes, and a complete 15-minute test; test longer scripts after that. Do not treat 15 minutes as a maximum.
7. Only after the 15-minute long-form prototype passes review, integrate the new renderer into the production workflow and retire stock-footage selection.
8. Preserve manual-only workflow dispatch, private YouTube upload, and one review artifact per render unless the user approves a change.

## Monetization and originality

This design is intended to support original educational storytelling and reduce the repetitive, stock-template appearance of the channel. It cannot guarantee YouTube monetization approval. Originality, meaningful educational value, editorial judgment, and variation across finished videos remain essential.
