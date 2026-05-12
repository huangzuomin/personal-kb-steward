from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.jinja_renderer import render_template


def render(item: dict) -> str:
    return render_template("official_material_handoff.j2", item)
