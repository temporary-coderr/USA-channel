from __future__ import annotations

"""WISE-LAB procedural SVG scene engine.

Creates original, script-directed vector illustrations without stock media or image APIs.
Run:
  python svg_animation_engine.py --script scripts/script.txt --output output/svg_prototype --format landscape
"""

import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path

PALETTE = {
    "navy": "#081321", "panel": "#12243A", "panel2": "#192F48",
    "teal": "#39D6D0", "blue": "#668BFF", "white": "#F4F7FB",
    "muted": "#A9BACB", "skin": "#E8B98D", "skin2": "#C98562",
    "hair": "#26364A", "gold": "#F3C969", "coral": "#FF806F",
    "green": "#80D6A5", "purple": "#B59AFF",
}

STOP = set("""
a an the and or but if then than of in on at to for from with by as is are was
were be been being it its this that these those you your we our they their he
she his her i me my us them what why how when where who which can could would
should will just very more most less much many some any not no do does did have
has had about into over after before between through during because while also
""".split())

TOPIC_RULES = [
    (("dog", "dogs", "puppy", "puppies", "canine", "pet dog"), "dog"),
    (("cat", "cats", "kitten", "kittens"), "cat"),
    (("bird", "birds", "parrot", "parrots"), "bird"),
    # Concrete objects take priority over broad cognitive terms. For example,
    # "phone notifications interrupt attention" must render a phone, not a brain.
    (("phone", "text", "message", "notification", "notifications", "social media", "screen"), "phone"),
    (("brain", "memory", "remember", "forget", "attention", "thought", "mind"), "brain"),
    (("door", "doorway", "room", "enter", "exit"), "door"),
    (("clock", "time", "deadline", "late", "waiting"), "clock"),
    (("mirror", "self-image", "identity", "reflection"), "mirror"),
    (("book", "reading", "learn", "learning", "knowledge", "study"), "book"),
    (("heart", "emotion", "love", "fear", "stress", "anxiety", "feeling"), "heart"),
    (("crowd", "people", "social", "everyone", "audience", "group"), "crowd"),
    (("eye", "watching", "noticed", "spotlight", "attention"), "eye"),
    (("puzzle", "problem", "solve", "solution", "complex"), "puzzle"),
]

ACTION_RULES = [
    (("avoid", "avoidance", "ignore", "ignored", "withdraw"), "turn_away"),
    (("remember", "memory", "recall", "forget"), "thinking"),
    (("notice", "noticed", "watch", "watching", "attention", "observe"), "looking"),
    (("talk", "speak", "conversation", "say", "tell", "communicate"), "talking"),
    (("choose", "decision", "decide", "option", "control"), "choosing"),
    (("walk", "leave", "enter", "move", "approach"), "walking"),
    (("fear", "scared", "surprise", "unexpected", "shock"), "surprised"),
    (("learn", "understand", "explain", "discover", "realize"), "explaining"),
]

def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)

def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)

def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text.lower())

def infer_subject(text: str) -> str:
    words = set(_tokens(text))
    for terms, subject in TOPIC_RULES:
        if words.intersection(terms):
            return subject
    return "human"

def infer_action(text: str) -> str:
    words = set(_tokens(text))
    for terms, action in ACTION_RULES:
        if words.intersection(terms):
            return action
    return "explaining"

def _sentences(script: str) -> list[str]:
    return [s.strip() for s in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", script.strip()) if s.strip()]

def plan_visual_beats(script: str, target_wpm: int = 140, target_seconds: float = 3.0) -> list[dict]:
    """Split complete narration into short, ordered visual beats; never discard words."""
    if target_wpm < 60 or target_wpm > 240:
        raise ValueError("target_wpm must be between 60 and 240")
    words_per_beat = max(4, round(target_wpm * target_seconds / 60))
    beats = []
    cursor = 0
    for sentence in _sentences(script):
        words = sentence.split()
        if not words:
            continue
        # Keep spoken/caption beats short enough to read comfortably on mobile.
        # Prefer punctuation when it lands near the target, but never let a beat
        # grow beyond two extra words just to wait for a comma.
        chunks, current = [], []
        for word in words:
            current.append(word)
            at_clause_end = re.search(r"[,;:]$", word) is not None
            if len(current) >= words_per_beat and (at_clause_end or len(current) >= words_per_beat + 1):
                chunks.append(" ".join(current)); current = []
        if current:
            chunks.append(" ".join(current))
        for chunk in chunks:
            count = len(chunk.split())
            duration = count / target_wpm * 60
            subject = infer_subject(chunk)
            # Dense conceptual visuals receive extra reading time by merging with
            # the next beat later in the renderer; the base planner preserves narration.
            beats.append({
                "id": f"beat-{len(beats)+1:04d}",
                "narration": chunk,
                "duration_seconds": round(duration, 3),
                "subject": subject,
                "action": infer_action(chunk),
                "visual_kind": "concept" if subject in {"brain", "heart", "puzzle", "eye"} else "illustration",
            })
            cursor += count
    if not beats:
        raise ValueError("The script contains no readable narration.")
    if " ".join(b["narration"] for b in beats).split() != script.split():
        raise RuntimeError("Visual beat planner failed its narration-preservation check.")
    return beats

def _svg_defs(seed: int) -> str:
    return f"""
    <defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="{PALETTE['navy']}"/><stop offset="1" stop-color="#142B43"/>
      </linearGradient>
      <linearGradient id="glow" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="{PALETTE['teal']}" stop-opacity=".32"/><stop offset="1" stop-color="{PALETTE['blue']}" stop-opacity=".04"/>
      </linearGradient>
      <filter id="soft"><feGaussianBlur stdDeviation="26"/></filter>
      <pattern id="grid" width="56" height="56" patternUnits="userSpaceOnUse">
        <path d="M56 0H0V56" fill="none" stroke="#A9BACB" stroke-opacity=".055" stroke-width="1"/>
      </pattern>
    </defs>"""

def _background(seed: int, width: int, height: int) -> str:
    x = 180 + seed % max(1, width - 360)
    y = 130 + (seed // 7) % max(1, height - 260)
    return f"""
    <rect width="{width}" height="{height}" fill="url(#bg)"/>
    <rect width="{width}" height="{height}" fill="url(#grid)"/>
    <circle cx="{x}" cy="{y}" r="{min(width,height)*.24:.0f}" fill="url(#glow)" filter="url(#soft)"/>
    <path d="M0 {height*.82:.0f} Q{width*.25:.0f} {height*.76:.0f} {width*.5:.0f} {height*.84:.0f} T{width} {height*.80:.0f} V{height} H0Z" fill="#07101D" opacity=".46"/>
    """

def _human(x: int, y: int, scale: float, action: str, seed: int, phase: float = 0.0) -> str:
    skin = PALETTE["skin"] if seed % 2 else PALETTE["skin2"]
    shirt = [PALETTE["teal"], PALETTE["blue"], PALETTE["purple"], "#E9EDF3"][seed % 4]
    arm = {
        "thinking": f'<path d="M-32 -25 Q-70 -65 -35 -95" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/><circle cx="-35" cy="-98" r="10" fill="{skin}"/>',
        "looking": f'<path d="M30 -25 Q75 -70 85 -65" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "talking": f'<path d="M30 -20 Q75 -5 90 -35" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "choosing": f'<path d="M30 -20 Q78 -45 95 -10" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "walking": f'<path d="M-30 -20 Q-70 5 -82 48 M30 -20 Q70 5 82 48" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "turn_away": f'<path d="M30 -25 Q65 -15 85 20" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "surprised": f'<path d="M-30 -25 Q-78 -85 -88 -55 M30 -25 Q78 -85 88 -55" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
        "explaining": f'<path d="M30 -20 Q75 -55 92 -90" fill="none" stroke="{skin}" stroke-width="18" stroke-linecap="round"/>',
    }.get(action, "")
    face = '<ellipse cx="0" cy="-130" rx="47" ry="55" fill="'+skin+'" stroke="#17263A" stroke-width="6"/>'
    hair = f'<path d="M-45 -145 Q-55 -205 0 -198 Q53 -202 47 -143 Q20 -170 -5 -160 Q-25 -150 -45 -145Z" fill="{PALETTE["hair"]}"/>'
    eyes = '<circle cx="-16" cy="-132" r="4" fill="#17263A"/><circle cx="16" cy="-132" r="4" fill="#17263A"/>'
    mouth = '<path d="M-10 -105 Q0 -98 10 -105" fill="none" stroke="#8F4D47" stroke-width="4" stroke-linecap="round"/>'
    bob = math.sin(phase * math.tau) * 5.0
    arm_swing = math.sin(phase * math.tau) * 8.0
    leg_swing = math.sin(phase * math.tau) * 12.0 if action == "walking" else 0.0
    legs = (f'<g><path d="M-22 55 L-30 120" stroke="#25364B" stroke-width="22" stroke-linecap="round" transform="rotate({leg_swing:.2f} -22 55)"/><path d="M22 55 L30 120" stroke="#25364B" stroke-width="22" stroke-linecap="round" transform="rotate({-leg_swing:.2f} 22 55)"/></g>')
    return f'<g transform="translate({x} {y + bob:.2f}) scale({scale})"><ellipse cx="0" cy="126" rx="66" ry="13" fill="#000" opacity=".24"/><path d="M-38 -75 Q0 -95 38 -75 L52 55 Q0 80 -52 55Z" fill="{shirt}" stroke="#17263A" stroke-width="7"/>{legs}<g transform="rotate({arm_swing:.2f} 0 -35)">{arm}</g>{face}{hair}{eyes}{mouth}</g>'

def _dog(x: int, y: int, scale: float, seed: int) -> str:
    coat = "#D8A66F" if seed % 2 else "#E7D7BE"
    return f'<g transform="translate({x} {y}) scale({scale})"><ellipse cx="0" cy="42" rx="112" ry="18" fill="#000" opacity=".22"/><path d="M-78 -12 Q-85 -72 -25 -74 Q45 -85 74 -35 L100 5 Q55 40 -52 25Z" fill="{coat}" stroke="#27364A" stroke-width="7"/><circle cx="78" cy="-54" r="47" fill="{coat}" stroke="#27364A" stroke-width="7"/><path d="M48 -84 Q5 -125 25 -48Z M95 -90 Q137 -120 117 -48Z" fill="{coat}" stroke="#27364A" stroke-width="7"/><circle cx="92" cy="-60" r="5" fill="#17263A"/><ellipse cx="122" cy="-35" rx="13" ry="9" fill="#17263A"/><path d="M-48 20 L-55 78 M40 22 L52 78" stroke="{coat}" stroke-width="18" stroke-linecap="round"/><path d="M-78 -18 Q-125 -45 -120 -82" fill="none" stroke="{coat}" stroke-width="17" stroke-linecap="round"/></g>'

def _cat(x: int, y: int, scale: float, seed: int) -> str:
    fur = "#C7CED8" if seed % 2 else "#D9A46F"
    return f'<g transform="translate({x} {y}) scale({scale})"><ellipse cx="0" cy="40" rx="92" ry="16" fill="#000" opacity=".22"/><path d="M-65 -5 Q-70 -78 0 -72 Q75 -78 70 -5 L55 50 L-55 50Z" fill="{fur}" stroke="#27364A" stroke-width="7"/><path d="M-55 -48 L-70 -120 L-12 -82Z M20 -82 L70 -120 L58 -42Z" fill="{fur}" stroke="#27364A" stroke-width="7"/><circle cx="-24" cy="-25" r="5" fill="#17263A"/><circle cx="24" cy="-25" r="5" fill="#17263A"/><path d="M-9 -2 L9 -2 L0 8Z" fill="#D98278"/><path d="M0 8 Q-20 24 -38 12 M0 8 Q20 24 38 12" fill="none" stroke="#27364A" stroke-width="4"/><path d="M-42 42 L-48 82 M42 42 L48 82" stroke="{fur}" stroke-width="16" stroke-linecap="round"/><path d="M62 18 Q115 15 100 -45" fill="none" stroke="{fur}" stroke-width="14" stroke-linecap="round"/></g>'

def _phone(x: int, y: int, scale: float) -> str:
    return f'<g transform="translate({x} {y}) scale({scale})"><rect x="-55" y="-100" width="110" height="200" rx="20" fill="#101B2B" stroke="{PALETTE["teal"]}" stroke-width="7"/><rect x="-43" y="-78" width="86" height="145" rx="8" fill="#203C55"/><circle cx="0" cy="83" r="7" fill="{PALETTE["muted"]}"/><rect x="-30" y="-58" width="60" height="12" rx="6" fill="{PALETTE["teal"]}"/><rect x="-30" y="-30" width="45" height="8" rx="4" fill="#A9BACB"/><rect x="-30" y="-10" width="60" height="8" rx="4" fill="#A9BACB" opacity=".7"/><circle cx="26" cy="35" r="13" fill="{PALETTE["coral"]}"/></g>'

def _brain(x: int, y: int, scale: float, seed: int) -> str:
    return f'<g transform="translate({x} {y}) scale({scale})"><path d="M0 -105 C-65 -155 -125 -105 -112 -45 C-155 5 -105 80 -50 70 C-20 125 30 115 45 75 C110 95 150 35 112 -15 C145 -85 75 -145 25 -110 C15 -145 -10 -145 0 -105Z" fill="#B59AFF" fill-opacity=".92" stroke="#E2D7FF" stroke-width="7"/><path d="M0 -102 Q-35 -50 -8 -5 Q-48 25 -30 70 M25 -100 Q65 -65 35 -30 Q80 5 52 55 M-80 -65 Q-45 -45 -65 -12 M80 -65 Q45 -40 72 -15" fill="none" stroke="#705BA8" stroke-width="8" stroke-linecap="round"/></g>'

def _object(subject: str, x: int, y: int, scale: float, seed: int) -> str:
    if subject == "phone": return _phone(x, y, scale)
    if subject == "brain": return _brain(x, y, scale, seed)
    if subject == "dog": return _dog(x, y, scale, seed)
    if subject == "cat": return _cat(x, y, scale, seed)
    if subject == "heart":
        return f'<g transform="translate({x} {y}) scale({scale})"><path d="M0 95 C-155 0 -120 -110 -45 -100 C-10 -98 0 -65 0 -65 C30 -125 145 -100 130 -15 C120 40 55 85 0 125Z" fill="{PALETTE["coral"]}" stroke="#FFD1C9" stroke-width="8"/></g>'
    if subject == "clock":
        return f'<g transform="translate({x} {y}) scale({scale})"><circle r="100" fill="#172D45" stroke="{PALETTE["teal"]}" stroke-width="10"/><path d="M0 -72 V0 L55 35" fill="none" stroke="{PALETTE["white"]}" stroke-width="12" stroke-linecap="round"/><circle r="9" fill="{PALETTE["gold"]}"/></g>'
    if subject == "door":
        return f'<g transform="translate({x} {y}) scale({scale})"><rect x="-80" y="-145" width="160" height="290" rx="8" fill="#8D6A4D" stroke="#E7C7A5" stroke-width="10"/><circle cx="48" cy="5" r="9" fill="{PALETTE["gold"]}"/><path d="M-65 -125 H65" stroke="#C79A70" stroke-width="6"/></g>'
    if subject == "mirror":
        return f'<g transform="translate({x} {y}) scale({scale})"><rect x="-105" y="-145" width="210" height="290" rx="100" fill="#24415B" stroke="{PALETTE["teal"]}" stroke-width="12"/><path d="M-60 -70 Q0 -125 60 -70 M-65 0 Q0 -55 65 0" fill="none" stroke="#C6F5F1" stroke-width="9" opacity=".75"/></g>'
    if subject == "book":
        return f'<g transform="translate({x} {y}) scale({scale})"><path d="M-5 -95 Q-90 -120 -125 -70 V95 Q-55 65 -5 100 Q55 65 125 95 V-70 Q55 -120 -5 -95Z" fill="#24415B" stroke="{PALETTE["teal"]}" stroke-width="8"/><path d="M-5 -90 V95 M-100 -45 Q-55 -60 -25 -35 M25 -35 Q65 -60 100 -45" fill="none" stroke="#E6F0F7" stroke-width="7"/></g>'
    if subject == "eye":
        return f'<g transform="translate({x} {y}) scale({scale})"><path d="M-145 0 Q0 -130 145 0 Q0 130 -145 0Z" fill="#EAF3F8" stroke="{PALETTE["teal"]}" stroke-width="9"/><circle r="52" fill="#4D7898"/><circle r="24" fill="#102238"/><circle cx="15" cy="-18" r="10" fill="white"/></g>'
    if subject == "puzzle":
        return f'<g transform="translate({x} {y}) scale({scale})"><path d="M-100 -100 H-25 Q-40 -45 0 -45 Q40 -45 25 -100 H100 V-25 Q45 -40 45 0 Q45 40 100 25 V100 H25 Q40 45 0 45 Q-40 45 -25 100 H-100 V25 Q-45 40 -45 0 Q-45 -40 -100 -25Z" fill="{PALETTE["blue"]}" stroke="#D9E3FF" stroke-width="8"/></g>'
    if subject == "crowd":
        people = []
        for i in range(5):
            px = x + (i-2)*65*scale
            py = y + (i%2)*24*scale
            people.append(_human(int(px), int(py), .42*scale, "explaining", seed+i))
        return "".join(people)
    return ""

def _callout(text: str, x: int, y: int, width: int) -> str:
    label = re.sub(r"\s+", " ", text).strip()
    label = label[:68] + ("…" if len(label) > 68 else "")
    return f'<g><rect x="{x}" y="{y}" width="{width}" height="76" rx="18" fill="#10243A" stroke="{PALETTE["teal"]}" stroke-opacity=".65" stroke-width="2"/><text x="{x+24}" y="{y+48}" fill="{PALETTE["white"]}" font-family="DejaVu Sans,sans-serif" font-size="25" font-weight="600">{_esc(label)}</text></g>'

def render_scene_svg(narration: str, beat_index: int, width: int = 1920, height: int = 1080, phase: float = 0.0) -> str:
    """Compose a fresh SVG scene from the narration's subject, action and stable seed."""
    seed = _seed(f"{beat_index}|{narration}")
    subject = infer_subject(narration)
    action = infer_action(narration)
    vertical = height > width
    cx = int(width * (.5 + ((seed % 17)-8)*.012))
    cy = int(height * (.55 + (((seed >> 4) % 9)-4)*.012))
    scale = min(width, height) / 720
    elements = []
    # A contextual human guide appears in most scenes, but not on every frame.
    show_person = subject not in {"dog", "cat"} or seed % 3 != 0
    if subject in {"dog", "cat"}:
        elements.append(_object(subject, int(width*.66), int(height*.61), scale*.72, seed))
        if show_person:
            elements.append(_human(int(width*.30), int(height*.72), scale*.72, action, seed, phase))
    elif subject == "crowd":
        elements.append(_object("crowd", int(width*.52), int(height*.72), scale, seed))
        elements.append(_object("eye", int(width*.78), int(height*.28), scale*.48, seed))
    elif subject in {"brain", "heart", "puzzle", "eye"}:
        elements.append(_human(int(width*.28), int(height*.72), scale*.76, action, seed, phase))
        elements.append(_object(subject, int(width*.69), int(height*.48), scale*.82, seed))
        elements.append(f'<path d="M{width*.42:.0f} {height*.48:.0f} Q{width*.53:.0f} {height*.28:.0f} {width*.57:.0f} {height*.43:.0f}" fill="none" stroke="{PALETTE["teal"]}" stroke-width="7" stroke-dasharray="12 14"/>')
    elif subject in {"phone", "door", "clock", "mirror", "book"}:
        elements.append(_human(int(width*.30), int(height*.72), scale*.72, action, seed, phase))
        elements.append(_object(subject, int(width*.70), int(height*.48), scale*.82, seed))
        elements.append(f'<path d="M{width*.42:.0f} {height*.55:.0f} Q{width*.53:.0f} {height*.34:.0f} {width*.58:.0f} {height*.48:.0f}" fill="none" stroke="{PALETTE["gold"]}" stroke-width="6" stroke-dasharray="9 12"/>')
    else:
        elements.append(_human(cx, int(height*.73), scale*.95, action, seed, phase))
        elements.append(_callout(" ".join([w for w in _tokens(narration) if w not in STOP][:5]) or "HUMAN BEHAVIOUR",
                                 int(width*.55), int(height*.20), int(width*.34)))
    # Short, editorially useful title; narration itself remains in the voice track.
    keywords = [w for w in _tokens(narration) if w not in STOP]
    title = " ".join(keywords[:5]).upper() or "THE HUMAN MIND"
    title = title[:22] if vertical else title[:42]
    title_y = int(height * (.12 if vertical else .16))
    title_size = int(min(width, height) * (.046 if vertical else .052))
    title_size = max(26, min(title_size, 64))
    text_x = int(width*.075)
    title_svg = f'<text x="{text_x}" y="{title_y}" fill="{PALETTE["white"]}" font-family="DejaVu Sans,sans-serif" font-size="{title_size}" font-weight="700" letter-spacing="1.5">{_esc(title)}</text>'
    accent = f'<rect x="{text_x}" y="{title_y+22}" width="{min(width*.18,250):.0f}" height="7" rx="3" fill="{PALETTE["teal"]}"/>'
    footer = f'<text x="{text_x}" y="{height-42}" fill="{PALETTE["muted"]}" font-family="DejaVu Sans,sans-serif" font-size="{max(18,int(min(width,height)*.018))}" letter-spacing="4">WISE LAB  /  EXPLORE THE MIND</text>'
    # Subtle numbered motif makes each beat identifiable without recycling a slide.
    number = f'<text x="{width-75}" y="{height-48}" text-anchor="end" fill="{PALETTE["teal"]}" opacity=".8" font-family="DejaVu Sans,sans-serif" font-size="28">{beat_index:03d}</text>'
    # Camera move: gentle push-in with a slow alternating pan. The frame renderer
    # supplies phase from 0..1 so each beat has continuous motion, not a static slide.
    phase = max(0.0, min(1.0, phase))
    zoom = 1.0 + 0.035 * math.sin(math.pi * phase)
    direction = -1 if seed % 2 else 1
    pan_x = direction * width * 0.012 * math.sin(math.pi * phase)
    pan_y = height * 0.006 * math.cos(math.pi * phase)
    camera = (f'translate({pan_x:.2f} {pan_y:.2f}) '
              f'translate({width/2:.2f} {height/2:.2f}) scale({zoom:.5f}) '
              f'translate({-width/2:.2f} {-height/2:.2f})')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            + _svg_defs(seed)
            + f'<g transform="translate({-pan_x*.22:.2f} {-pan_y*.22:.2f})">' + _background(seed, width, height) + '</g>'
            + f'<g transform="{camera}">' + "".join(elements) + title_svg + accent + footer + number + '</g></svg>')

def build_script_visuals(script_path: Path, output_dir: Path, video_format: str = "landscape",
                         target_wpm: int = 140, target_seconds: float = 3.0) -> dict:
    script = script_path.read_text(encoding="utf-8").strip()
    vertical = video_format.lower() == "shorts"
    width, height = (1080, 1920) if vertical else (1920, 1080)
    beats = plan_visual_beats(script, target_wpm, target_seconds)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    try:
        import cairosvg
    except ImportError as exc:
        raise RuntimeError("CairoSVG is required. Install it with: pip install CairoSVG") from exc
    manifest = {
        "engine": "WISE-LAB Procedural SVG Scene Engine",
        "version": 1,
        "source_script": str(script_path),
        "format": video_format,
        "dimensions": [width, height],
        "stock_media_used": False,
        "external_image_apis_used": False,
        "beat_count": len(beats),
        "beats": [],
    }
    for index, beat in enumerate(beats, 1):
        svg = render_scene_svg(beat["narration"], index, width, height)
        svg_path = scenes_dir / f"{beat['id']}.svg"
        png_path = scenes_dir / f"{beat['id']}.png"
        svg_path.write_text(svg, encoding="utf-8")
        cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path),
                         output_width=width, output_height=height)
        if not png_path.exists() or png_path.stat().st_size < 1500:
            raise RuntimeError(f"SVG scene {beat['id']} rendered an empty image.")
        manifest["beats"].append({
            **beat, "svg_file": str(svg_path.relative_to(output_dir)),
            "png_file": str(png_path.relative_to(output_dir)),
            "sha256": hashlib.sha256(png_path.read_bytes()).hexdigest(),
        })
    if len(manifest["beats"]) != len(beats):
        raise RuntimeError("Not every planned visual beat was rendered.")
    (output_dir / "visual_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate original WISE-LAB SVG images from a narration script.")
    parser.add_argument("--script", default="scripts/script.txt")
    parser.add_argument("--output", default="output/svg_prototype")
    parser.add_argument("--format", choices=("landscape", "shorts"), default="landscape")
    parser.add_argument("--wpm", type=int, default=140)
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()
    manifest = build_script_visuals(Path(args.script), Path(args.output), args.format, args.wpm, args.seconds)
    print(f"Generated {manifest['beat_count']} original SVG scenes.")
    print(f"SVG and PNG previews: {Path(args.output) / 'scenes'}")
    print("Stock media: none. External image-generation APIs: none.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
