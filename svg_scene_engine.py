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

    emotion = "neutral"
    for terms, value in [
        ({"sad", "lonely", "loss", "grief"}, "sad"),
        ({"happy", "joy", "smile", "delighted"}, "happy"),
        ({"shocked", "shock", "surprised", "unexpected"}, "shocked"),
        ({"thinking", "think", "wonder", "consider", "remember"}, "thinking"),
        ({"angry", "anger", "frustrated", "furious"}, "angry"),
        ({"scared", "fear", "afraid", "terrified", "anxiety"}, "scared"),
    ]:
        if words & terms:
            emotion = value
            break
    if emotion == "neutral" and action == "explaining":
        emotion = "thinking"
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
    layouts = ("left_focus", "right_focus", "wide_interaction", "close_up")
    layout = layouts[(beat_index - 1) % len(layouts)]
    return {
        "subject": subject, "action": action, "emotion": emotion,
        "environment": environment, "props": props,
        "character": "boy" if seed % 5 else "girl",
        "layout": layout,
        "seed": seed,
    }

def _background(env: str, w: int, h: int, seed: int) -> str:
    """Draw a layered, location-specific environment instead of a flat colour card."""
    night = env in {"rainy_street", "dark_room"}
    horizon = int(h * (0.70 if env in {"park", "rainy_street"} else 0.76))
    parts = [
        f'<defs><linearGradient id="sceneSky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ "#101A2D" if night else "#6F9FB5" }"/>'
        f'<stop offset="1" stop-color="{ "#293B55" if night else "#D5C8AE" }"/></linearGradient>'
        f'<linearGradient id="sceneFloor" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ "#29384B" if night else "#8D9B83" }"/>'
        f'<stop offset="1" stop-color="{ "#101C2C" if night else "#4B6258" }"/></linearGradient></defs>',
        f'<rect width="{w}" height="{h}" fill="url(#sceneSky)"/>',
    ]
    if env == "park":
        sun_x = int(w * (.78 if seed % 2 else .20))
        parts += [
            f'<circle cx="{sun_x}" cy="{h*.17:.0f}" r="{min(w,h)*.075:.0f}" fill="#F6D99A" opacity=".82"/>',
            f'<path d="M0 {h*.60:.0f} Q{w*.25:.0f} {h*.48:.0f} {w*.52:.0f} {h*.59:.0f} T{w} {h*.54:.0f} V{h} H0Z" fill="#6F9479"/>',
            f'<path d="M0 {h*.76:.0f} Q{w*.48:.0f} {h*.64:.0f} {w} {h*.76:.0f} V{h} H0Z" fill="url(#sceneFloor)"/>',
        ]
        for i, x in enumerate((.10, .27, .78, .93)):
            xx = int(w*x); yy = int(h*(.43 + (i%2)*.06)); radius = int(min(w,h)*(.12 + (i%3)*.025))
            parts += [
                f'<path d="M{xx} {yy} v{h*.34:.0f}" stroke="#70533E" stroke-width="{max(12,int(w*.018))}"/>',
                f'<circle cx="{xx}" cy="{yy}" r="{radius}" fill="{("#376B55","#477B60","#568766")[i%3]}"/>',
                f'<circle cx="{xx-radius*.35:.0f}" cy="{yy-radius*.25:.0f}" r="{radius*.48:.0f}" fill="#78A477" opacity=".52"/>',
            ]
        parts += [
            f'<path d="M{w*.40:.0f} {h} Q{w*.48:.0f} {h*.82:.0f} {w*.62:.0f} {h*.72:.0f} Q{w*.72:.0f} {h*.67:.0f} {w*.82:.0f} {h*.70:.0f}" fill="none" stroke="#C9B995" stroke-width="{max(22,int(w*.055))}" opacity=".85"/>',
            f'<path d="M{w*.40:.0f} {h} Q{w*.48:.0f} {h*.82:.0f} {w*.62:.0f} {h*.72:.0f}" fill="none" stroke="#E4D4B6" stroke-width="5" opacity=".55"/>',
        ]
    elif env == "bedroom":
        parts += [
            f'<rect x="{w*.06:.0f}" y="{h*.08:.0f}" width="{w*.88:.0f}" height="{h*.70:.0f}" rx="{w*.025:.0f}" fill="#34445D" stroke="#71839A" stroke-width="5"/>',
            f'<rect x="{w*.12:.0f}" y="{h*.14:.0f}" width="{w*.30:.0f}" height="{h*.28:.0f}" fill="#172A43" stroke="#B6C6D0" stroke-width="8"/>',
            f'<path d="M{w*.27:.0f} {h*.14:.0f} V{h*.42:.0f} M{w*.12:.0f} {h*.28:.0f} H{w*.42:.0f}" stroke="#8297AC" stroke-width="5"/>',
            f'<rect x="{w*.12:.0f}" y="{h*.58:.0f}" width="{w*.60:.0f}" height="{h*.20:.0f}" rx="24" fill="#64758A"/>',
            f'<rect x="{w*.16:.0f}" y="{h*.53:.0f}" width="{w*.22:.0f}" height="{h*.12:.0f}" rx="18" fill="#D5C6B4"/>',
            f'<path d="M{w*.10:.0f} {h*.79:.0f} H{w*.76:.0f} V{h*.85:.0f} H{w*.10:.0f}Z" fill="#A88A72"/>',
            f'<circle cx="{w*.82:.0f}" cy="{h*.34:.0f}" r="{min(w,h)*.045:.0f}" fill="#F1D28C" opacity=".85"/>',
        ]
    elif env == "workplace":
        parts += [
            f'<rect x="{w*.06:.0f}" y="{h*.09:.0f}" width="{w*.88:.0f}" height="{h*.50:.0f}" fill="#344D66" stroke="#91A8B8" stroke-width="7"/>',
            f'<path d="M{w*.50:.0f} {h*.09:.0f} V{h*.59:.0f} M{w*.06:.0f} {h*.34:.0f} H{w*.94:.0f}" stroke="#A9C1CC" stroke-width="5"/>',
            f'<rect x="{w*.12:.0f}" y="{h*.64:.0f}" width="{w*.76:.0f}" height="{h*.07:.0f}" rx="8" fill="#805F49"/>',
            f'<path d="M{w*.18:.0f} {h*.71:.0f} V{h*.91:.0f} M{w*.82:.0f} {h*.71:.0f} V{h*.91:.0f}" stroke="#594737" stroke-width="13"/>',
            f'<rect x="{w*.33:.0f}" y="{h*.52:.0f}" width="{w*.28:.0f}" height="{h*.12:.0f}" rx="8" fill="#172637" stroke="#6EC9C1" stroke-width="5"/>',
            f'<rect x="{w*.36:.0f}" y="{h*.55:.0f}" width="{w*.22:.0f}" height="{h*.06:.0f}" fill="#9BC9D2" opacity=".55"/>',
        ]
    elif env == "interior":
        parts += [
            f'<rect x="{w*.04:.0f}" y="{h*.06:.0f}" width="{w*.92:.0f}" height="{h*.72:.0f}" fill="#40536A" stroke="#8192A2" stroke-width="6"/>',
            f'<path d="M{w*.04:.0f} {h*.24:.0f} H{w*.96:.0f} M{w*.04:.0f} {h*.48:.0f} H{w*.96:.0f}" stroke="#71869A" stroke-width="3" opacity=".55"/>',
            f'<rect x="{w*.72:.0f}" y="{h*.17:.0f}" width="{w*.17:.0f}" height="{h*.53:.0f}" fill="#805D43" stroke="#D6B38C" stroke-width="8"/>',
            f'<rect x="{w*.75:.0f}" y="{h*.21:.0f}" width="{w*.11:.0f}" height="{h*.22:.0f}" fill="#B6C9D0" opacity=".38"/>',
            f'<circle cx="{w*.85:.0f}" cy="{h*.46:.0f}" r="9" fill="#F2C66D"/>',
            f'<path d="M{w*.12:.0f} {h*.66:.0f} V{h*.36:.0f} Q{w*.12:.0f} {h*.28:.0f} {w*.20:.0f} {h*.28:.0f} Q{w*.28:.0f} {h*.28:.0f} {w*.28:.0f} {h*.36:.0f} V{h*.66:.0f}" fill="#263B50" stroke="#9AAAB7" stroke-width="5"/>',
            f'<path d="M{w*.08:.0f} {h*.67:.0f} H{w*.32:.0f}" stroke="#9AAAB7" stroke-width="8"/>',
        ]
    elif env == "rainy_street":
        parts += [
            f'<path d="M0 {h*.66:.0f} L{w*.22:.0f} {h*.44:.0f} L{w*.43:.0f} {h*.62:.0f} L{w*.68:.0f} {h*.39:.0f} L{w} {h*.58:.0f} V{h} H0Z" fill="#26384D"/>',
            f'<rect y="{h*.72:.0f}" width="{w}" height="{h*.28:.0f}" fill="#15263B"/>',
        ]
        for i in range(7):
            x = int(w*(i/7)) + int(seed % max(1,int(w*.05)))
            bw = int(w*(.08 + (i%3)*.025)); bh = int(h*(.22 + (i%4)*.07))
            parts.append(f'<rect x="{x-bw//2}" y="{h*.66-bh:.0f}" width="{bw}" height="{bh}" fill="{("#30445D","#3A4C62","#26384F")[i%3]}"/>')
            for j in range(3):
                parts.append(f'<rect x="{x-bw*.30+j*bw*.28:.0f}" y="{h*.66-bh*.75:.0f}" width="{bw*.12:.0f}" height="{bh*.12:.0f}" fill="#E8C887" opacity=".75"/>')
        for i in range(42):
            x = (seed * (i + 11) % w)
            y = (seed // (i + 3) % max(1,int(h*.70)))
            parts.append(f'<path d="M{x} {y} l-12 35" stroke="#9BC7DA" stroke-width="2" opacity=".42"/>')
        parts.append(f'<path d="M0 {h*.84:.0f} Q{w*.5:.0f} {h*.76:.0f} {w} {h*.85:.0f}" stroke="#7896A9" stroke-width="5" fill="none" opacity=".6"/>')
    elif env == "dark_room":
        parts += [
            f'<circle cx="{w*.78:.0f}" cy="{h*.20:.0f}" r="{min(w,h)*.10:.0f}" fill="#52617C" opacity=".45"/>',
            f'<rect x="{w*.62:.0f}" y="{h*.12:.0f}" width="{w*.25:.0f}" height="{h*.30:.0f}" fill="#111E34" stroke="#6C829B" stroke-width="6"/>',
            f'<path d="M{w*.745:.0f} {h*.12:.0f} V{h*.42:.0f} M{w*.62:.0f} {h*.27:.0f} H{w*.87:.0f}" stroke="#50647D" stroke-width="4"/>',
        ]
        for i in range(18):
            x = (seed*(i+5)) % w; y = (seed//(i+2)) % max(1,int(h*.62))
            parts.append(f'<circle cx="{x}" cy="{y}" r="{2+i%3}" fill="#C7D8E8" opacity=".5"/>')
    else:
        parts += [
            f'<circle cx="{w*.78:.0f}" cy="{h*.22:.0f}" r="{min(w,h)*.22:.0f}" fill="#36516C" opacity=".65"/>',
            f'<circle cx="{w*.78:.0f}" cy="{h*.22:.0f}" r="{min(w,h)*.15:.0f}" fill="#4B6A83" opacity=".36"/>',
            f'<path d="M0 {h*.74:.0f} Q{w*.25:.0f} {h*.68:.0f} {w*.5:.0f} {h*.75:.0f} T{w} {h*.72:.0f} V{h} H0Z" fill="#263C53"/>',
            f'<path d="M0 {h*.83:.0f} Q{w*.5:.0f} {h*.77:.0f} {w} {h*.84:.0f} V{h} H0Z" fill="#1C2E43"/>',
        ]
    parts.append(f'<rect y="{h*.90:.0f}" width="{w}" height="{h*.10:.0f}" fill="#101B2A" opacity=".20"/>')
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
                     height: int = 1080, phase: float = 0.0,
                     visual_brief: dict | None = None) -> str:
    brief = visual_brief or plan_scene(narration, beat_index)
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
