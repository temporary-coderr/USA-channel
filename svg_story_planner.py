from __future__ import annotations

"""Groq-powered story planner with deterministic SVG-scene fallback."""

import json
import os
import re
from typing import Any

import requests

from svg_scene_engine import plan_scene

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

ALLOWED = {
    "subject": {"human", "dog", "cat", "phone", "door", "brain", "heart", "clock", "book", "mirror", "crowd", "eye"},
    "action": {"explaining", "walking", "sitting", "pointing", "hiding", "waving", "talking", "thinking", "shocked", "scared", "angry", "sad", "happy"},
    "emotion": {"neutral", "sad", "happy", "shocked", "thinking", "angry", "scared"},
    "environment": {"rainy_street", "bedroom", "park", "workplace", "interior", "dark_room", "studio"},
    "character": {"boy", "girl"},
    "layout": {"left_focus", "right_focus", "wide_interaction", "close_up"},
    "props": {"phone", "broken_phone", "door", "brain", "heart", "clock", "book", "coffee", "dog", "cat"},
}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Groq response did not contain JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        raise ValueError("Groq response must contain a scenes array")
    return value


def _validate_scene(raw: Any, beat: dict, index: int) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Scene entry is not an object")
    result = plan_scene(str(beat.get("narration", "")), index)
    for field in ("subject", "action", "emotion", "environment", "character", "layout"):
        value = raw.get(field)
        if isinstance(value, str) and value in ALLOWED[field]:
            result[field] = value
    props = raw.get("props", [])
    if isinstance(props, list):
        result["props"] = list(dict.fromkeys(
            p for p in props if isinstance(p, str) and p in ALLOWED["props"]
        ))[:4]
    # The procedural renderer only supports the named geometry above.
    result["seed"] = plan_scene(str(beat.get("narration", "")), index)["seed"]
    return result


def _prompt(beats: list[dict]) -> str:
    compact = [
        {"beat_index": i, "narration": str(beat.get("narration", ""))[:700]}
        for i, beat in enumerate(beats, 1)
    ]
    return (
        "You are the storyboard director for WISE-LAB, an original educational "
        "2D flat-vector animation channel. Plan one distinct, visually literal "
        "scene for every narration beat. Do not invent facts or add text. "
        "Choose only from the exact allowed values below. Make each scene "
        "specific to its narration; vary layouts across adjacent beats. For "
        "dog or cat beats, set subject to dog or cat and include that animal "
        "in props. Choose an action and emotion that match the meaning, not "
        "just a repeated default. Keep props limited to objects that the SVG "
        "renderer can draw. Return JSON only, in this exact shape: "
        '{"scenes":[{"beat_index":1,"subject":"human","action":"thinking",'
        '"emotion":"thinking","environment":"studio","props":[],"character":"boy",'
        '"layout":"left_focus"}]}. '
        "Allowed subject: human,dog,cat,phone,door,brain,heart,clock,book,mirror,crowd,eye. "
        "Allowed action: explaining,walking,sitting,pointing,hiding,waving,talking,thinking,shocked,scared,angry,sad,happy. "
        "Allowed emotion: neutral,sad,happy,shocked,thinking,angry,scared. "
        "Allowed environment: rainy_street,bedroom,park,workplace,interior,dark_room,studio. "
        "Allowed props: phone,broken_phone,door,brain,heart,clock,book,coffee,dog,cat. "
        "Allowed character: boy,girl. Allowed layout: left_focus,right_focus,wide_interaction,close_up. "
        "For each beat return exactly one scene, preserving beat_index. "
        "Narration beats:\n" + json.dumps(compact, ensure_ascii=False)
    )


def plan_story(beats: list[dict], timeout: int = 35) -> tuple[list[dict], dict]:
    """Use Groq once per video; gracefully fall back beat-by-beat."""
    fallback = [plan_scene(str(b.get("narration", "")), i)
                for i, b in enumerate(beats, 1)]
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return fallback, {"provider": "rules_fallback", "reason": "GROQ_API_KEY not configured"}

    model = os.getenv("GROQ_STORY_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    payload = {
        "model": model,
        "temperature": 0.35,
        "max_tokens": min(6000, max(1200, len(beats) * 130)),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Return valid JSON only. Follow the schema and allowed values exactly."},
            {"role": "user", "content": _prompt(beats)},
        ],
    }
    try:
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        indexed = {}
        for item in parsed["scenes"]:
            if isinstance(item, dict) and isinstance(item.get("beat_index"), int):
                indexed[item["beat_index"]] = item
        scenes = []
        ai_count = 0
        for i, beat in enumerate(beats, 1):
            raw = indexed.get(i)
            try:
                scenes.append(_validate_scene(raw, beat, i) if raw else fallback[i-1])
                ai_count += int(raw is not None)
            except (TypeError, ValueError):
                scenes.append(fallback[i-1])
        if ai_count == 0:
            raise ValueError("Groq returned no usable scene briefs")
        return scenes, {
            "provider": "groq",
            "model": model,
            "planned_scene_count": ai_count,
            "fallback_scene_count": len(beats) - ai_count,
        }
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        # Never print API credentials or full response bodies in CI logs.
        return fallback, {
            "provider": "rules_fallback",
            "reason": f"Groq planner unavailable or invalid ({type(exc).__name__})",
        }
