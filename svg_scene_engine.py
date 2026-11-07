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
    elif words & {"cafe", "coffee", "restaurant", "barista", "cappuccino"}:
        environment = "cafe"
    elif words & {"school", "student", "teacher", "classroom", "lecture"}:
        environment = "classroom"
    elif words & {"city", "street", "traffic", "commute", "subway", "train"}:
        environment = "city"
    elif words & {"bedroom", "sleep", "nightmare", "bed"}:
        environment = "bedroom"
    elif words & {"home", "family", "parent", "kitchen", "living"}:
        environment = "home"
    elif words & {"park", "outside", "walk", "walking", "dog", "dogs", "garden", "tree"}:
        environment = "park"
    elif words & {"office", "work", "coworker", "meeting", "computer"}:
        environment = "workplace"
    elif words & {"door", "doorway", "room", "enter", "exit"}:
        environment = "interior"
    elif words & {"dark", "lonely", "alone", "fear", "scared", "anxiety"}:
        environment = "dark_room"
    else:
        environments = ("studio", "interior", "park", "bedroom", "cafe", "classroom", "city", "home")
        environment = environments[_seed(narration + str(beat_index)) % len(environments)]

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
    """Build a scene-specific, seeded environment with real layout variation."""
    variant = seed % 5
    palettes = [
        ("#15243A", "#314D65", "#D5C6AE", "#344A42", "#EFCB86"),
        ("#20243B", "#514568", "#E4CBB8", "#53606D", "#F0B58D"),
        ("#18313A", "#3D6670", "#D9D0B8", "#4B665A", "#E6D28D"),
        ("#302B2B", "#725B52", "#E6D8C4", "#6D6252", "#E7B66F"),
        ("#172B45", "#49647A", "#D6DCE0", "#566B75", "#B9D8E7"),
    ]
    sky_top, sky_bottom, wall, floor, accent = palettes[variant]
    parts = [
        '<defs>'
        f'<linearGradient id="sky{seed:x}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky_top}"/><stop offset="1" stop-color="{sky_bottom}"/></linearGradient>'
        f'<linearGradient id="floor{seed:x}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{floor}"/><stop offset="1" stop-color="#101B2A"/></linearGradient>'
        '</defs>',
        f'<rect width="{w}" height="{h}" fill="url(#sky{seed:x})"/>',
    ]
    # Every environment gets a different composition seed, not just a colour swap.
    if env == "park":
        horizon = h * (0.48 + (variant % 3) * 0.045)
        parts += [
            f'<circle cx="{w*(.18 + .16*variant):.0f}" cy="{h*(.14 + .025*(variant%2)):.0f}" r="{min(w,h)*.065:.0f}" fill="{accent}" opacity=".9"/>',
            f'<path d="M0 {horizon:.0f} Q{w*.24:.0f} {h*(.38+variant*.012):.0f} {w*.52:.0f} {horizon+18:.0f} T{w} {horizon-12:.0f} V{h} H0Z" fill="#6F9479"/>',
        ]
        tree_xs = [(.08,.30,.73,.93),(.16,.43,.66,.88),(.04,.24,.61,.82),(.12,.37,.79,.98),(.20,.48,.70,.91)][variant]
        for i, xf in enumerate(tree_xs):
            x = int(w*xf); y = int(h*(.39 + ((i+variant)%3)*.035))
            r = int(min(w,h)*(.075 + ((i+variant)%3)*.018))
            parts += [
                f'<path d="M{x} {y} v{h*.37:.0f}" stroke="#70533E" stroke-width="{max(12,int(w*.018))}"/>',
                f'<circle cx="{x}" cy="{y}" r="{r}" fill="{("#376B55","#477B60","#568766")[(i+variant)%3]}"/>',
                f'<circle cx="{x-r*.3:.0f}" cy="{y-r*.3:.0f}" r="{r*.42:.0f}" fill="#9AB889" opacity=".45"/>',
            ]
        parts += [f'<path d="M{w*(.22+.04*variant):.0f} {h} Q{w*.45:.0f} {h*.82:.0f} {w*(.56+.025*variant):.0f} {h*.72:.0f} T{w} {h*.74:.0f}" stroke="#D9C7A5" stroke-width="{max(22,int(w*.06))}" fill="none"/>']
    elif env in {"bedroom", "home"}:
        parts += [
            f'<rect x="0" y="0" width="{w}" height="{h*.78:.0f}" fill="{wall}"/>',
            f'<rect x="{w*(.07+.055*variant):.0f}" y="{h*.10:.0f}" width="{w*(.25+.02*(variant%2)):.0f}" height="{h*.27:.0f}" rx="8" fill="#20364D" stroke="#D0D6D2" stroke-width="7"/>',
            f'<path d="M{w*(.195+.055*variant):.0f} {h*.10:.0f} V{h*.37:.0f} M{w*(.07+.055*variant):.0f} {h*.235:.0f} H{w*(.32+.075*variant):.0f}" stroke="#91A9B8" stroke-width="5"/>',
            f'<rect x="{w*(.10+.035*variant):.0f}" y="{h*(.55-.025*(variant%2)):.0f}" width="{w*(.55+.035*(variant%3)):.0f}" height="{h*.24:.0f}" rx="24" fill="#64758A"/>',
            f'<rect x="{w*(.14+.035*variant):.0f}" y="{h*.51:.0f}" width="{w*.20:.0f}" height="{h*.10:.0f}" rx="16" fill="#D5C6B4"/>',
            f'<rect x="{w*(.73-.04*variant):.0f}" y="{h*.38:.0f}" width="{w*.10:.0f}" height="{h*.39:.0f}" fill="#805D43"/>',
            f'<path d="M{w*(.78-.04*variant):.0f} {h*.38:.0f} v{h*.39:.0f}" stroke="#D6B38C" stroke-width="6"/>',
            f'<circle cx="{w*(.84-.035*variant):.0f}" cy="{h*.33:.0f}" r="{min(w,h)*.035:.0f}" fill="{accent}"/>',
        ]
        if env == "home":
            parts += [f'<rect x="{w*.06:.0f}" y="{h*.68:.0f}" width="{w*.22:.0f}" height="{h*.11:.0f}" rx="12" fill="#9A7355"/>',
                      f'<path d="M{w*.09:.0f} {h*.68:.0f} q{w*.075:.0f} {-h*.17:.0f} {w*.15:.0f} 0" fill="#6F9479"/>']
    elif env == "workplace":
        parts += [
            f'<rect width="{w}" height="{h*.76:.0f}" fill="{wall}"/>',
            f'<rect x="{w*(.06+.06*variant):.0f}" y="{h*.08:.0f}" width="{w*.72:.0f}" height="{h*.40:.0f}" fill="#344D66" stroke="#A9C1CC" stroke-width="7"/>',
            f'<path d="M{w*(.30+.06*variant):.0f} {h*.08:.0f} V{h*.48:.0f} M{w*(.06+.06*variant):.0f} {h*.28:.0f} H{w*(.78+.06*variant):.0f}" stroke="#A9C1CC" stroke-width="5"/>',
            f'<rect x="{w*(.08+.04*variant):.0f}" y="{h*(.59+.015*(variant%2)):.0f}" width="{w*.78:.0f}" height="{h*.075:.0f}" rx="8" fill="#805F49"/>',
            f'<path d="M{w*.16:.0f} {h*.665:.0f} V{h*.91:.0f} M{w*.80:.0f} {h*.665:.0f} V{h*.91:.0f}" stroke="#594737" stroke-width="13"/>',
            f'<rect x="{w*(.32+.04*variant):.0f}" y="{h*.46:.0f}" width="{w*.23:.0f}" height="{h*.14:.0f}" rx="9" fill="#172637" stroke="#6EC9C1" stroke-width="5"/>',
        ]
    elif env in {"interior", "studio"}:
        parts += [
            f'<rect width="{w}" height="{h*.80:.0f}" fill="{wall}"/>',
            f'<path d="M{w*.04:.0f} {h*.16:.0f} H{w*.96:.0f} M{w*.04:.0f} {h*.43:.0f} H{w*.96:.0f}" stroke="#A5B1B8" stroke-width="4" opacity=".35"/>',
            f'<rect x="{w*(.64-.04*variant):.0f}" y="{h*.14:.0f}" width="{w*.20:.0f}" height="{h*.53:.0f}" fill="#805D43" stroke="#D6B38C" stroke-width="7"/>',
            f'<circle cx="{w*(.79-.04*variant):.0f}" cy="{h*.44:.0f}" r="9" fill="{accent}"/>',
            f'<rect x="{w*(.08+.035*variant):.0f}" y="{h*.20:.0f}" width="{w*.22:.0f}" height="{h*.25:.0f}" fill="#263B50" stroke="#9AAAB7" stroke-width="5"/>',
            f'<path d="M{w*.12:.0f} {h*.45:.0f} h{w*.14:.0f}" stroke="#9AAAB7" stroke-width="8"/>',
        ]
        if env == "studio":
            parts += [f'<circle cx="{w*(.48+.025*variant):.0f}" cy="{h*.28:.0f}" r="{min(w,h)*(.12+.012*variant):.0f}" fill="{accent}" opacity=".20"/>',
                      f'<path d="M{w*.08:.0f} {h*.72:.0f} Q{w*.5:.0f} {h*(.60+.02*variant):.0f} {w*.92:.0f} {h*.72:.0f}" stroke="#9EB0BE" stroke-width="5" fill="none" opacity=".5"/>']
    elif env == "rainy_street":
        parts += [f'<rect width="{w}" height="{h}" fill="#17283D"/>']
        for i in range(7):
            x = int(w*((i+.5)/7)) + int((seed >> (i%8)) % max(1,int(w*.035)))
            bw = int(w*(.07+((i+variant)%3)*.025)); bh = int(h*(.25+((i+variant)%4)*.065))
            parts.append(f'<rect x="{x-bw//2}" y="{h*.70-bh:.0f}" width="{bw}" height="{bh}" fill="{("#30445D","#3A4C62","#26384F")[(i+variant)%3]}"/>')
            for j in range(3):
                wy = h*.70-bh*.78 + ((j+variant)%2)*h*.06
                parts.append(f'<rect x="{x-bw*.30+j*bw*.28:.0f}" y="{wy:.0f}" width="{bw*.12:.0f}" height="{bh*.12:.0f}" fill="{accent}" opacity=".8"/>')
        for i in range(32):
            x = (seed*(i+11) % w); y = (seed//(i+2) % max(1,int(h*.70)))
            parts.append(f'<path d="M{x} {y} l-10 34" stroke="#9BC7DA" stroke-width="2" opacity=".42"/>')
        parts += [f'<path d="M0 {h*.83:.0f} Q{w*.5:.0f} {h*(.75+.015*variant):.0f} {w} {h*.85:.0f}" stroke="#7896A9" stroke-width="6" fill="none"/>']
    elif env == "city":
        parts += [f'<rect width="{w}" height="{h}" fill="#26384D"/>']
        for i in range(8):
            bw = w*(.09+((i+variant)%3)*.025); bh = h*(.28+((i*2+variant)%5)*.07)
            x = w*(i/8)-bw*.2
            parts.append(f'<rect x="{x:.0f}" y="{h*.74-bh:.0f}" width="{bw:.0f}" height="{bh:.0f}" fill="{("#34465B","#40536A","#293D52")[(i+variant)%3]}"/>')
            for j in range(2):
                parts.append(f'<rect x="{x+bw*.25+j*bw*.35:.0f}" y="{h*.74-bh*.72:.0f}" width="{bw*.12:.0f}" height="{h*.035:.0f}" fill="{accent}" opacity=".75"/>')
        parts += [f'<path d="M0 {h*.74:.0f} H{w} V{h} H0Z" fill="#1B2B3E"/>',
                  f'<path d="M{w*.12:.0f} {h*.86:.0f} H{w*.88:.0f}" stroke="#D3C3A4" stroke-width="5" stroke-dasharray="36 30" opacity=".55"/>']
    elif env == "cafe":
        parts += [f'<rect width="{w}" height="{h*.78:.0f}" fill="{wall}"/>',
                  f'<rect x="{w*.08:.0f}" y="{h*.12:.0f}" width="{w*.34:.0f}" height="{h*.34:.0f}" fill="#29465A" stroke="#D7C7AE" stroke-width="7"/>',
                  f'<path d="M{w*.25:.0f} {h*.12:.0f} V{h*.46:.0f} M{w*.08:.0f} {h*.29:.0f} H{w*.42:.0f}" stroke="#D7C7AE" stroke-width="4"/>',
                  f'<rect x="{w*(.52+.025*variant):.0f}" y="{h*.18:.0f}" width="{w*.34:.0f}" height="{h*.16:.0f}" rx="12" fill="#6D4D3B"/>',
                  f'<path d="M{w*.10:.0f} {h*.68:.0f} H{w*.90:.0f}" stroke="#A87B55" stroke-width="{max(20,int(w*.05))}"/>',
                  f'<path d="M{w*.18:.0f} {h*.68:.0f} V{h*.90:.0f} M{w*.82:.0f} {h*.68:.0f} V{h*.90:.0f}" stroke="#654A39" stroke-width="12"/>',
                  f'<circle cx="{w*(.70+.025*variant):.0f}" cy="{h*.53:.0f}" r="{min(w,h)*.045:.0f}" fill="{accent}"/>']
    elif env == "classroom":
        parts += [f'<rect width="{w}" height="{h*.80:.0f}" fill="{wall}"/>',
                  f'<rect x="{w*.10:.0f}" y="{h*.12:.0f}" width="{w*.80:.0f}" height="{h*.30:.0f}" fill="#24443F" stroke="#D2C7B2" stroke-width="8"/>',
                  f'<path d="M{w*.18:.0f} {h*.25:.0f} q{w*.12:.0f} {-h*.05:.0f} {w*.22:.0f} 0 M{w*.52:.0f} {h*.32:.0f} q{w*.12:.0f} {-h*.06:.0f} {w*.20:.0f} 0" stroke="#DCE5D8" stroke-width="5" fill="none"/>',
                  f'<rect x="{w*.08:.0f}" y="{h*.58:.0f}" width="{w*.84:.0f}" height="{h*.06:.0f}" fill="#805F49"/>',
                  f'<path d="M{w*.15:.0f} {h*.64:.0f} V{h*.90:.0f} M{w*.85:.0f} {h*.64:.0f} V{h*.90:.0f}" stroke="#594737" stroke-width="12"/>']
    else:
        # A fallback landscape is still a designed place, not a blank colour card.
        parts += [f'<circle cx="{w*(.70-.025*variant):.0f}" cy="{h*.20:.0f}" r="{min(w,h)*.16:.0f}" fill="{accent}" opacity=".5"/>',
                  f'<path d="M0 {h*.68:.0f} Q{w*.25:.0f} {h*(.60+.02*variant):.0f} {w*.5:.0f} {h*.68:.0f} T{w} {h*.67:.0f} V{h} H0Z" fill="#405B62"/>']
    parts += [
        f'<rect y="{h*.88:.0f}" width="{w}" height="{h*.12:.0f}" fill="url(#floor{seed:x})" opacity=".42"/>',
        f'<path d="M0 {h*.94:.0f} Q{w*.5:.0f} {h*(.90+.008*variant):.0f} {w} {h*.94:.0f}" stroke="#FFFFFF" stroke-width="3" opacity=".08" fill="none"/>',
    ]
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
    if name == "mirror":
        return f'<g transform="translate({x:.0f} {y:.0f})"><rect x="-55" y="-105" width="110" height="190" rx="52" fill="#A8C4D1" stroke="#E9E1D4" stroke-width="12"/><ellipse cx="0" cy="-10" rx="34" ry="70" fill="#D5E1E5" opacity=".7"/></g>'
    if name == "eye":
        return f'<g transform="translate({x:.0f} {y:.0f})"><path d="M-105 0 Q0 -90 105 0 Q0 90 -105 0Z" fill="#F3E8D7" stroke="#31577A" stroke-width="9"/><circle r="35" fill="#6D9DB8"/><circle r="16" fill="#101B2A"/></g>'
    if name == "keys":
        return f'<g transform="translate({x:.0f} {y:.0f})" fill="none" stroke="#EFCB86" stroke-width="12"><circle cx="-30" cy="0" r="22"/><path d="M-8 0 H75 V18 H55 V34 H38 V18"/></g>'
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
        dog_x = person_x + (width*.22 if person_x < width/2 else -width*.22)
        dog_y = height*.72
        dog = _dog(dog_x, dog_y, scale*.78, seed, phase)
        # Flip the dog when it is on the right so its muzzle faces the person.
        if person_x < width/2:
            dog = f'<g transform="translate({2*dog_x:.1f} 0) scale(-1 1)">{dog}</g>'
        prop += dog
        words = _tokens(narration)
        if words & {"love", "bond", "oxytocin", "gaze", "eyes", "eye", "look", "looking"}:
            heart_x = (person_x + dog_x) / 2
            heart_y = height*.48
            prop += (f'<g transform="translate({heart_x:.1f} {heart_y:.1f}) scale({scale*.30:.3f})"><path d="M0 55 C-115 -15 -80 -100 0 -35 C80 -100 115 -15 0 55Z" fill="#EF8175" stroke="#FFD1C9" stroke-width="7"/></g>')
    if brief["subject"] == "cat":
        prop += _cat(prop_x, height*.76, scale*.62, seed, phase)
    camera_zoom = 1 + .025 * math.sin(math.pi * phase)
    pan = math.sin(math.pi * phase) * (1 if seed % 2 else -1) * width*.008
    camera = (f'translate({pan:.1f} 0) translate({width/2:.1f} {height/2:.1f}) '
              f'scale({camera_zoom:.4f}) translate({-width/2:.1f} {-height/2:.1f})')
    # No baked-in repetitive title/footer: the scene itself carries the visual meaning.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<g>{bg}</g><g transform="{camera}">{character}{prop}</g></svg>')
