from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SkillSpec:
    name: str
    slug: str
    description: str
    path: Path
    frontmatter: dict[str, Any]
    body: str


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not match:
        return {}, text
    data: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, match.group(2)


def load_skill(root: Path, skill_name: str) -> SkillSpec:
    path = root / "skills" / skill_name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    frontmatter, body = parse_frontmatter(text)
    return SkillSpec(
        name=str(frontmatter.get("name") or skill_name),
        slug=skill_name,
        description=str(frontmatter.get("description") or ""),
        path=path,
        frontmatter=frontmatter,
        body=body,
    )


def build_system_prompt(spec: SkillSpec) -> str:
    return "\n".join([
        "You are executing an OpenClaw personal knowledge-base Skill.",
        "Follow the SKILL.md contract exactly.",
        "Return JSON only. Do not return Markdown outside JSON.",
        "Do not invent sources. Use only the provided source paths.",
        "Do not create resolved Obsidian wikilinks for pages not present in context.",
        "Put uncertain links into pending_links.",
        "Put low confidence, missing source, conflict, or unsafe actions into manual_review.",
        "",
        f"Skill slug: {spec.slug}",
        f"Skill name: {spec.name}",
        f"Description: {spec.description}",
        "",
        "SKILL.md:",
        spec.body,
    ])
