from __future__ import annotations

import html
import re
from pathlib import Path

import cairosvg


STOP = set("the a an and or but if then than of in on at to for from with by as is are was were be been being it its this that these those you your we our they their he she his her i me my us them what why how when where who which can could would should will just very more most less much many some any not no do does did have has had about into over after before between through during because while also".split())


def _terms(text: str) -> list[str]:
    words = []
    for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text.lower()):
        if word not in STOP and word not in words:
            words.append(word)
        if len(words) >= 5:
            break
    return words or ["attention", "thoughts", "emotion", "behaviour"]


def build_topic_diagram(text: str, destination: Path, vertical: bool, sequence: int) -> Path:
    """Create an original topic-specific explainer graphic using words from the narration."""
    width, height = (720, 1280) if vertical else (1280, 720)
    title_words = re.findall(r"[A-Za-z][A-Za-z'-]+", text)[:7]
    title = " ".join(title_words) or "A psychology concept"
    labels = _terms(text)[:4]
    while len(labels) < 4:
        labels.append(["context", "response", "reflection", "choice"][len(labels)])
    safe_title = html.escape(title[:64])
    safe_labels = [html.escape(label[:24].title()) for label in labels]
    lowered = text.lower()
    if any(term in lowered for term in ("cycle", "loop", "overthinking", "habit", "anxiety")):
        layout = "loop"
    elif any(term in lowered for term in ("versus", "compared", "difference", "whereas", "rather than")):
        layout = "compare"
    elif any(term in lowered for term in ("first", "then", "steps", "stages", "process")):
        layout = "process"
    else:
        layout = "map"
    bg = "#081321"
    teal = "#39D6D0"
    blue = "#5577FF"
    white = "#F3F7FB"
    muted = "#B8C8D8"
    nodes = []
    if layout == "loop":
        centers = [(width*.5,height*.34),(width*.78,height*.53),(width*.5,height*.72),(width*.22,height*.53)]
        for i,(x,y) in enumerate(centers):
            nodes.append(f'<rect x="{x-width*.13:.1f}" y="{y-height*.035:.1f}" width="{width*.26:.1f}" height="{height*.07:.1f}" rx="22" fill="#14283E" stroke="{teal if i%2==0 else blue}" stroke-width="4"/><text x="{x:.1f}" y="{y+9:.1f}" text-anchor="middle" fill="{white}" font-size="{width*.023:.1f}" font-family="DejaVu Sans">{safe_labels[i]}</text>')
        for i,(x,y) in enumerate(centers):
            nx,ny=centers[(i+1)%4]
            nodes.append(f'<path d="M{x:.1f},{y+height*.05:.1f} Q{(x+nx)/2+20:.1f},{(y+ny)/2:.1f} {nx:.1f},{ny-height*.05:.1f}" fill="none" stroke="{teal}" stroke-width="5" stroke-linecap="round" opacity=".85"/>')
    elif layout == "compare":
        for i,x in enumerate((width*.28,width*.72)):
            nodes.append(f'<rect x="{x-width*.19:.1f}" y="{height*.34:.1f}" width="{width*.38:.1f}" height="{height*.32:.1f}" rx="28" fill="#14283E" stroke="{teal if i==0 else blue}" stroke-width="5"/><text x="{x:.1f}" y="{height*.43:.1f}" text-anchor="middle" fill="{teal if i==0 else blue}" font-size="{width*.025:.1f}" font-family="DejaVu Sans" font-weight="bold">{("PERSPECTIVE A","PERSPECTIVE B")[i]}</text><text x="{x:.1f}" y="{height*.53:.1f}" text-anchor="middle" fill="{white}" font-size="{width*.023:.1f}" font-family="DejaVu Sans">{safe_labels[i*2]}</text><text x="{x:.1f}" y="{height*.59:.1f}" text-anchor="middle" fill="{muted}" font-size="{width*.018:.1f}" font-family="DejaVu Sans">{safe_labels[i*2+1]}</text>')
        nodes.append(f'<path d="M{width*.48:.1f},{height*.5:.1f} L{width*.52:.1f},{height*.5:.1f}" stroke="{teal}" stroke-width="5"/>')
    elif layout == "process":
        for i,x in enumerate((width*.17,width*.39,width*.61,width*.83)):
            nodes.append(f'<circle cx="{x:.1f}" cy="{height*.52:.1f}" r="{width*.055:.1f}" fill="#14283E" stroke="{teal if i%2==0 else blue}" stroke-width="5"/><text x="{x:.1f}" y="{height*.53:.1f}" text-anchor="middle" fill="{white}" font-size="{width*.019:.1f}" font-family="DejaVu Sans">{safe_labels[i]}</text>')
            if i<3:
                nodes.append(f'<path d="M{x+width*.06:.1f},{height*.52:.1f} L{x+width*.16:.1f},{height*.52:.1f}" stroke="{teal}" stroke-width="5"/>')
    else:
        cx,cy=width*.5,height*.54
        positions=[(width*.25,height*.39),(width*.75,height*.39),(width*.25,height*.72),(width*.75,height*.72)]
        for i,(x,y) in enumerate(positions):
            nodes.append(f'<path d="M{cx:.1f},{cy:.1f} L{x:.1f},{y:.1f}" stroke="{teal if i%2==0 else blue}" stroke-width="4" opacity=".8"/><rect x="{x-width*.13:.1f}" y="{y-height*.045:.1f}" width="{width*.26:.1f}" height="{height*.09:.1f}" rx="20" fill="#14283E" stroke="{teal if i%2==0 else blue}" stroke-width="4"/><text x="{x:.1f}" y="{y+8:.1f}" text-anchor="middle" fill="{white}" font-size="{width*.022:.1f}" font-family="DejaVu Sans">{safe_labels[i]}</text>')
        nodes.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{width*.105:.1f}" fill="#102D3D" stroke="{teal}" stroke-width="6"/><text x="{cx:.1f}" y="{cy+8:.1f}" text-anchor="middle" fill="{white}" font-size="{width*.022:.1f}" font-family="DejaVu Sans" font-weight="bold">CORE IDEA</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#39D6D0"/><stop offset="1" stop-color="#5577FF"/></linearGradient></defs>
<rect width="100%" height="100%" fill="{bg}"/>
<circle cx="{width*.88:.1f}" cy="{height*.12:.1f}" r="{width*.2:.1f}" fill="url(#g)" opacity=".07"/>
<text x="{width*.07:.1f}" y="{height*.13:.1f}" fill="{teal}" font-size="{width*.018:.1f}" font-family="DejaVu Sans" letter-spacing="5">WISE LAB • VISUAL EXPLAINER {sequence:02d}</text>
<text x="{width*.07:.1f}" y="{height*.23:.1f}" fill="{white}" font-size="{width*.035:.1f}" font-family="DejaVu Sans" font-weight="bold">{safe_title}</text>
{''.join(nodes)}
<path d="M{width*.07:.1f},{height*.9:.1f} L{width*.93:.1f},{height*.9:.1f}" stroke="{teal}" opacity=".5" stroke-width="2"/>
<text x="{width*.07:.1f}" y="{height*.95:.1f}" fill="{muted}" font-size="{width*.014:.1f}" font-family="DejaVu Sans">Concept illustration • Not a scientific data chart</text>
</svg>'''
    svg_path = destination.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(destination), output_width=width, output_height=height)
    return destination
