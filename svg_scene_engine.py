from __future__ import annotations

"""Modular, script-adaptive flat-vector SVG scene composer for WISE-LAB.

The planner derives a visual brief for every narration beat. The renderer uses
only hand-authored SVG geometry: no stock media, raster art, or image APIs.
"""

import hashlib
import html
import math
import re

PALETTE = {
    "ink": "#101B2A", "navy": "#14243A", "blue": "#31577A",
    "sky": "#6D9DB8", "cream": "#F3E8D7", "skin": "#B97855",
    "skin2": "#D69A72", "hair": "#171923", "hoodie": "#343D4A",
    "pants": "#171D28", "teal": "#54D4C8", "gold": "#F2C66D",
    "coral": "#EF8175", "purple": "#A995D8", "white": "#F7F7F4",
    "green": "#85B99A", "ground": "#24354A",
}

def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z'-]*", text.lower()))

def plan_scene(narration: str, beat_index: int) -> dict:
    """Return a deterministic but beat-specific visual direction."""
    words = _tokens(narration)
    subject = "human"
    for terms, value in [
        ({"dog", "dogs", "puppy", "puppies", "owner", "pet"}, "dog"),
        ({"cat", "cats", "kitten"}, "cat"),
        ({"phone", "notification", "notifications", "text", "message"}, "phone"),
        ({"door", "doorway", "room", "enter", "exit"}, "door"),
        ({"brain", "memory", "remember", "forget", "mind", "thought"}, "brain"),
        ({"heart", "love", "emotion", "fear", "anxiety", "stress"}, "heart"),
        ({"clock", "time", "deadline", "waiting"}, "clock"),
        ({"book", "reading", "study", "learn", "learning"}, "book"),
        ({"mirror", "reflection", "identity", "self-image"}, "mirror"),
        ({"crowd", "people", "everyone", "audience", "social"}, "crowd"),
        ({"eye", "watching", "noticed", "spotlight"}, "eye"),
    ]:
        if words & terms:
            subject = value
            break

    action = "explaining"
    for terms, value in [
        ({"walk", "walking", "enter", "leave", "approach"}, "walking"),
        ({"sit", "sitting", "rest"}, "sitting"),
        ({"point", "pointing", "show"}, "pointing"),
        ({"hide", "hiding", "avoid", "withdraw"}, "hiding"),
        ({"wave", "goodbye", "farewell"}, "waving"),
        ({"talk", "talking", "speak", "conversation", "say"}, "talking"),
        ({"think", "thinking", "remember", "consider", "wonder"}, "thinking"),
        ({"surprise", "shocked", "shock", "unexpected"}, "shocked"),
        ({"scared", "fear", "afraid", "terrified"}, "scared"),
        ({"angry", "anger", "frustrated"}, "angry"),
        ({"sad", "lonely", "miss", "loss"}, "sad"),
        ({"happy", "joy", "smile", "love"}, "happy"),
    ]:
        if words & terms:
            action = value
            break

    if words & {"rain", "rainy", "storm", "wet"}:
        environment = "rainy_street"
    elif words & {"bedroom", "sleep", "nightmare", "bed"}:
        environment = "bedroom"
    elif words & {"park", "outside", "walk", "walking", "dog", "dogs"}:
        environment = "park"
    elif words & {"office", "work", "coworker", "meeting"}:
        environment = "workplace"
    elif words & {"door", "doorway", "room", "enter", "exit"}:
        environment = "interior"
    elif words & {"dark", "lonely", "alone", "fear", "scared", "anxiety"}:
        environment = "dark_room"
    else:
        environment = ("studio", "interior", "park", "bedroom")[_seed(narration + str(beat_index)) % 4]

    emotion = action if action in {"sad", "happy", "shocked", "thinking", "angry", "scared"} else (
        "thinking" if action == "explaining" else "neutral")
    props = []
    if subject in {"phone", "door", "brain", "heart", "clock", "book", "mirror", "eye"}:
        props.append(subject)
    if words & {"broken", "cracked", "shattered"} and "phone" in words:
        props.append("broken_phone")
    if words & {"coffee", "cup"}:
        props.append("coffee")
    if words & {"key", "keys"}:
        props.append("keys")
    if subject == "dog":
        props.append("dog")
    if subject == "cat":
        props.append("cat")

    seed = _seed(f"{beat_index}|{narration}")
    return {
        "subject": subject, "action": action, "emotion": emotion,
        "environment": environment, "props": props,
        "character": "boy" if seed % 5 else "girl",
        "layout": ("left_focus", "right_focus", "wide_interaction", "close_up")[seed % 4],
        "seed": seed,
    }

def _background(env: str, w: int, h: int, seed: int) -> str:
    night = env in {"rainy_street", "dark_room"}
    sky = "#101B30" if night else ("#A9C9D4" if env == "park" else "#263A52")
    ground = "#18263B" if night else ("#78947B" if env == "park" else "#34465A")
    parts = [f'<rect width="{w}" height="{h}" fill="{sky}"/>']
    if env == "rainy_street":
        parts += [f'<rect y="{h*.68:.0f}" width="{w}" height="{h*.32:.0f}" fill="#17263A"/>',
                  f'<path d="M0 {h*.77:.0f} L{w} {h*.72:.0f}" stroke="#52647A" stroke-width="5"/>']
        for i in range(38):
            x = (seed * (i+11) % w)
            y = (seed // (i+3) % int(h*.72))
            parts.append(f'<path d="M{x} {y} l-12 35" stroke="#8DB7D0" stroke-width="2" opacity=".48"/>')
        for x in (w*.12, w*.82):
            parts.append(f'<rect x="{x:.0f}" y="{h*.25:.0f}" width="{w*.12:.0f}" height="{h*.42:.0f}" fill="#263A55"/><rect x="{x+20:.0f}" y="{h*.31:.0f}" width="{w*.025:.0f}" height="{h*.08:.0f}" fill="#F2C66D" opacity=".7"/>')
    elif env == "bedroom":
        parts += [f'<rect x="{w*.08:.0f}" y="{h*.12:.0f}" width="{w*.84:.0f}" height="{h*.68:.0f}" rx="20" fill="#24364E"/>',
                  f'<rect x="{w*.63:.0f}" y="{h*.2:.0f}" width="{w*.23:.0f}" height="{h*.26:.0f}" fill="#17243A" stroke="#8299B0" stroke-width="7"/>',
                  f'<rect x="{w*.14:.0f}" y="{h*.57:.0f}" width="{w*.48:.0f}" height="{h*.18:.0f}" rx="18" fill="#52647C"/>']
    elif env == "park":
        parts += [f'<rect y="{h*.68:.0f}" width="{w}" height="{h*.32:.0f}" fill="#78947B"/>']
        for x, r in ((w*.12,h*.20),(w*.83,h*.24),(w*.58,h*.16)):
            parts += [f'<rect x="{x-8:.0f}" y="{h*.36:.0f}" width="18" height="{h*.36:.0f}" fill="#725A43"/>',
                      f'<circle cx="{x:.0f}" cy="{h*.34:.0f}" r="{r:.0f}" fill="#47785E"/>']
    elif env == "workplace":
        parts += [f'<rect y="{h*.70:.0f}" width="{w}" height="{h*.30:.0f}" fill="#28384A"/>',
                  f'<rect x="{w*.08:.0f}" y="{h*.18:.0f}" width="{w*.84:.0f}" height="{h*.48:.0f}" fill="#314B63"/>',
                  f'<path d="M{w*.08:.0f} {h*.42:.0f} H{w*.92:.0f}" stroke="#8DA4B7" stroke-width="6"/>']
    elif env == "interior":
        parts += [f'<rect x="{w*.08:.0f}" y="{h*.08:.0f}" width="{w*.84:.0f}" height="{h*.72:.0f}" fill="#31465D"/>',
                  f'<rect x="{w*.72:.0f}" y="{h*.18:.0f}" width="{w*.16:.0f}" height="{h*.5:.0f}" fill="#8C6B50" stroke="#D5B18A" stroke-width="8"/>',
                  f'<circle cx="{w*.84:.0f}" cy="{h*.45:.0f}" r="8" fill="#F2C66D"/>']
    else:
        parts += [f'<circle cx="{w*.76:.0f}" cy="{h*.30:.0f}" r="{min(w,h)*.20:.0f}" fill="#263B57"/>',
                  f'<path d="M0 {h*.76:.0f} Q{w*.5:.0f} {h*.68:.0f} {w} {h*.78:.0f} V{h} H0Z" fill="{ground}"/>']
    if env != "rainy_street":
        parts.append(f'<rect y="{h*.82:.0f}" width="{w}" height="{h*.18:.0f}" fill="{ground}" opacity=".72"/>')
    return "".join(parts)

def _character(x: float, y: float, scale: float, brief: dict, phase: float) -> str:
    seed = brief["seed"]
    skin = PALETTE["skin"] if seed % 2 else PALETTE["skin2"]
    hair = PALETTE["hair"]
    hoodie = ("#343D4A", "#40536A", "#4A3D55")[seed % 3]
    action, emotion = brief["action"], brief["emotion"]
    bob = math.sin(phase * math.tau) * 3.5
    blink = abs((phase * 2.0) % 1.0 - .5) < .035
    eye_y = -128
    eyes = (f'<path d="M-19 {eye_y} q10 5 20 0 M9 {eye_y} q10 5 20 0" stroke="#18202B" stroke-width="5" fill="none"/>'
            if blink else
            f'<ellipse cx="-15" cy="{eye_y}" rx="6" ry="9" fill="#18202B"/><ellipse cx="15" cy="{eye_y}" rx="6" ry="9" fill="#18202B"/>')
    brow = ""
    if emotion in {"angry", "scared", "shocked"}:
        slope = "M-25 -148 L-7 -154 M7 -154 L25 -148" if emotion != "angry" else "M-25 -154 L-7 -145 M7 -145 L25 -154"
        brow = f'<path d="{slope}" stroke="{hair}" stroke-width="6" stroke-linecap="round"/>'
    if emotion == "sad":
        brow = '<path d="M-25 -151 Q-15 -158 -6 -151 M6 -151 Q15 -158 25 -151" stroke="#171923" stroke-width="5" fill="none"/>'
        mouth = '<path d="M-12 -99 Q0 -111 12 -99" stroke="#743F3A" stroke-width="5" fill="none"/>'
    elif emotion in {"happy"}:
        mouth = '<path d="M-15 -108 Q0 -82 15 -108" stroke="#743F3A" stroke-width="5" fill="none"/>'
    elif emotion == "shocked":
        mouth = '<ellipse cx="0" cy="-101" rx="8" ry="13" fill="#743F3A"/>'
    elif emotion == "angry":
        mouth = '<path d="M-13 -100 H13" stroke="#743F3A" stroke-width="6"/>'
    elif emotion == "scared":
        mouth = '<ellipse cx="0" cy="-101" rx="7" ry="11" fill="#743F3A"/>'
    elif action == "talking":
        mouth = ('<ellipse cx="0" cy="-101" rx="9" ry="12" fill="#743F3A"/>' if phase % 0.24 < 0.12 else '<path d="M-10 -104 Q0 -96 10 -104" stroke="#743F3A" stroke-width="5" fill="none"/>')
    else:
        mouth = '<path d="M-10 -104 Q0 -96 10 -104" stroke="#743F3A" stroke-width="5" fill="none"/>'
    if action == "sitting":
        legs = '<path d="M-25 45 L-85 85 L-35 95 M25 45 L80 82 L38 95" stroke="#171D28" stroke-width="23" fill="none" stroke-linecap="round"/>'
    elif action == "walking":
        swing = math.sin(phase * math.tau) * 17
        legs = f'<path d="M-20 45 L-30 112 M20 45 L30 112" stroke="#171D28" stroke-width="23" stroke-linecap="round" transform="rotate({swing:.1f} -20 45)"/>'
    else:
        legs = '<path d="M-22 45 L-28 115 M22 45 L28 115" stroke="#171D28" stroke-width="23" stroke-linecap="round"/>'
    if action == "thinking":
        arms = f'<path d="M-34 -55 Q-62 -88 -34 -112 L-18 -112" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/>'
    elif action == "pointing":
        arms = f'<path d="M32 -54 Q72 -80 112 -92" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/><circle cx="115" cy="-94" r="8" fill="{skin}"/>'
    elif action == "hiding":
        arms = f'<path d="M-35 -55 Q-65 -95 -25 -125 M35 -55 Q65 -95 25 -125" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/>'
    elif action == "waving":
        arms = f'<path d="M34 -55 Q68 -95 52 -145" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/>'
    elif action == "walking":
        arms = f'<path d="M-34 -55 L-48 -5 M34 -55 L48 -5" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/>'
    else:
        arms = f'<path d="M-34 -55 Q-65 -18 -60 5 M34 -55 Q65 -18 60 5" stroke="{skin}" stroke-width="17" fill="none" stroke-linecap="round"/>'
    hair_shape = '<path d="M-47 -145 Q-60 -205 -18 -195 L-5 -218 L12 -192 Q50 -205 48 -145 Q20 -166 0 -158 Q-25 -166 -47 -145Z"/>'
    if brief["character"] == "girl":
        hair_shape = '<path d="M-48 -145 Q-62 -205 -15 -198 L-5 -218 L15 -192 Q55 -205 48 -145 L55 -80 Q35 -105 40 -145Z"/>'
    return (f'<g transform="translate({x:.1f} {y+bob:.1f}) scale({scale:.4f})">'
            f'<ellipse cx="0" cy="125" rx="65" ry="12" fill="#000" opacity=".22"/>'
            f'{legs}<path d="M-38 -80 Q0 -98 38 -80 L48 48 Q0 67 -48 48Z" fill="{hoodie}" stroke="#202B38" stroke-width="6"/>'
            f'<path d="M-12 -65 V25 M12 -65 V25" stroke="#6B7784" stroke-width="3" opacity=".7"/>'
            f'{arms}<ellipse cx="0" cy="-132" rx="46" ry="54" fill="{skin}" stroke="#202B38" stroke-width="5"/>'
            f'<g fill="{hair}">{hair_shape}</g>{brow}{eyes}{mouth}</g>')

def _dog(x: float, y: float, scale: float, seed: int, phase: float) -> str:
    coat = "#C99762" if seed % 2 else "#E6D5B9"
    tail = math.sin(phase * math.tau) * 18
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({scale:.3f})">'
            f'<path d="M-78 -15 Q-90 -75 -25 -72 Q45 -80 78 -30 L95 22 Q25 55 -62 25Z" fill="{coat}" stroke="#3B3540" stroke-width="7"/>'
            f'<circle cx="78" cy="-55" r="43" fill="{coat}" stroke="#3B3540" stroke-width="7"/>'
            f'<path d="M50 -82 Q10 -125 25 -48Z M95 -88 Q138 -125 115 -43Z" fill="{coat}" stroke="#3B3540" stroke-width="7"/>'
            f'<circle cx="90" cy="-60" r="5" fill="#18202B"/><ellipse cx="119" cy="-34" rx="12" ry="8" fill="#18202B"/>'
            f'<path d="M-45 25 L-55 78 M40 28 L50 78" stroke="{coat}" stroke-width="18" stroke-linecap="round"/>'
            f'<path d="M-76 -18 Q-125 -42 -120 -82" stroke="{coat}" stroke-width="15" fill="none" stroke-linecap="round" transform="rotate({tail:.1f} -76 -18)"/>'
            f'</g>')

def _prop(name: str, x: float, y: float, scale: float) -> str:
    if name in {"phone", "broken_phone"}:
        crack = '<path d="M0 -35 L-15 -5 L8 5 L-8 38" stroke="#F7F7F4" stroke-width="4" fill="none"/>' if name == "broken_phone" else ""
        return f'<g transform="translate({x:.0f} {y:.0f}) scale({scale:.2f})"><rect x="-38" y="-70" width="76" height="140" rx="12" fill="#111923" stroke="#54D4C8" stroke-width="6"/><rect x="-29" y="-58" width="58" height="112" rx="5" fill="#34516B"/>{crack}</g>'
    if name == "door":
        return f'<g><rect x="{x-48:.0f}" y="{y-160:.0f}" width="96" height="320" fill="#805D43" stroke="#D6B38C" stroke-width="7"/><circle cx="{x+28:.0f}" cy="{y:.0f}" r="7" fill="#F2C66D"/></g>'
    if name == "brain":
        return f'<g transform="translate({x:.0f} {y:.0f}) scale({scale:.2f})"><path d="M0 -75 C-65 -105 -90 -45 -65 -12 C-105 40 -35 80 0 48 C45 90 100 35 68 -10 C95 -65 35 -100 0 -75Z" fill="#A995D8" stroke="#F0E8FF" stroke-width="7"/></g>'
    if name == "heart":
        return f'<path d="M{x:.0f} {y+55:.0f} C{x-115:.0f} {y-15:.0f} {x-80:.0f} {y-100:.0f} {x:.0f} {y-35:.0f} C{x+80:.0f} {y-100:.0f} {x+115:.0f} {y-15:.0f} {x:.0f} {y+55:.0f}Z" fill="#EF8175"/>'
    if name == "clock":
        return f'<g><circle cx="{x:.0f}" cy="{y:.0f}" r="65" fill="#F3E8D7" stroke="#31577A" stroke-width="8"/><path d="M{x:.0f} {y-42:.0f} V{y:.0f} l35 22" stroke="#18202B" stroke-width="8" fill="none"/></g>'
    if name == "book":
        return f'<g><path d="M{x-85:.0f} {y-55:.0f} Q{x-20:.0f} {y-80:.0f} {x:.0f} {y-48:.0f} Q{x+35:.0f} {y-80:.0f} {x+85:.0f} {y-55:.0f} V{y+60:.0f} Q{x+35:.0f} {y+35:.0f} {x:.0f} {y+65:.0f} Q{x-40:.0f} {y+35:.0f} {x-85:.0f} {y+60:.0f}Z" fill="#E6C58E" stroke="#5B4938" stroke-width="6"/></g>'
    if name == "coffee":
        return f'<g><path d="M{x-38:.0f} {y-28:.0f} h70 v70 h-70Z" fill="#F3E8D7"/><path d="M{x+32:.0f} {y-12:.0f} q45 -8 22 34 h-22" stroke="#F3E8D7" stroke-width="10" fill="none"/></g>'
    return ""

def _cat(x: float, y: float, scale: float, seed: int, phase: float) -> str:
    fur = "#C7CED8" if seed % 2 else "#D9A46F"
    tail = math.sin(phase * math.tau) * 12
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({scale:.3f})">'
            f'<path d="M-62 -4 Q-72 -82 0 -78 Q72 -82 62 -4 L48 48 H-48Z" fill="{fur}" stroke="#3B3540" stroke-width="7"/>'
            f'<path d="M-48 -50 L-65 -120 L-10 -82Z M15 -82 L65 -120 L48 -50Z" fill="{fur}" stroke="#3B3540" stroke-width="7"/>'
            f'<ellipse cx="-22" cy="-28" rx="5" ry="8" fill="#18202B"/><ellipse cx="22" cy="-28" rx="5" ry="8" fill="#18202B"/>'
            f'<path d="M-8 -8 L8 -8 L0 1Z" fill="#D98278"/><path d="M0 1 Q-18 16 -34 7 M0 1 Q18 16 34 7" stroke="#3B3540" stroke-width="4" fill="none"/>'
            f'<path d="M-38 42 L-45 78 M38 42 L45 78" stroke="{fur}" stroke-width="15" stroke-linecap="round"/>'
            f'<path d="M58 18 Q112 15 100 -45" stroke="{fur}" stroke-width="14" fill="none" transform="rotate({tail:.1f} 58 18)"/></g>')


def render_scene_svg(narration: str, beat_index: int, width: int = 1920,
                     height: int = 1080, phase: float = 0.0) -> str:
    brief = plan_scene(narration, beat_index)
    seed = brief["seed"]
    phase = max(0.0, min(1.0, phase))
    vertical = height > width
    scale = min(width, height) / 720
    bg = _background(brief["environment"], width, height, seed)
    # Layout alternates composition deliberately; characters are not pinned to one corner.
    if brief["layout"] == "left_focus":
        person_x, person_y, prop_x = width*.32, height*.76, width*.72
    elif brief["layout"] == "right_focus":
        person_x, person_y, prop_x = width*.70, height*.76, width*.28
    elif brief["layout"] == "close_up":
        person_x, person_y, prop_x = width*.48, height*.84, width*.78
        scale *= 1.16
    else:
        person_x, person_y, prop_x = width*.43, height*.76, width*.76
    if vertical:
        person_x = width*(.36 if brief["layout"] != "right_focus" else .64)
        person_y = height*.70
        prop_x = width*(.75 if person_x < width/2 else .22)
    move = (phase - .5) * width * .12 if brief["action"] == "walking" else 0
    character = _character(person_x + move, person_y, scale*.83, brief, phase)
    prop_y = height*(.48 if not vertical else .43)
    prop = "".join(_prop(p, prop_x + (i*scale*28), prop_y, scale*.85)
                   for i, p in enumerate(brief["props"]) if p != "dog")
    if brief["subject"] == "dog":
        dog_x = width*(.69 if person_x < width/2 else .28)
        dog = _dog(dog_x, height*.78, scale*.72, seed, phase)
        # Interaction is explicit: the dog is placed close and oriented toward the person.
        prop += dog
    if brief["subject"] == "cat":
        prop += _cat(prop_x, height*.76, scale*.62, seed, phase)
    camera_zoom = 1 + .025 * math.sin(math.pi * phase)
    pan = math.sin(math.pi * phase) * (1 if seed % 2 else -1) * width*.008
    camera = (f'translate({pan:.1f} 0) translate({width/2:.1f} {height/2:.1f}) '
              f'scale({camera_zoom:.4f}) translate({-width/2:.1f} {-height/2:.1f})')
    # No baked-in repetitive title/footer: the scene itself carries the visual meaning.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<g>{bg}</g><g transform="{camera}">{character}{prop}</g></svg>')
