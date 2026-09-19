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


def build_system_prompt(spec: SkillSpec, contract: dict[str, Any] | None = None) -> str:
    lines = [
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
    ]
    if contract:
        lines.extend([
            "",
            "输出契约（字段名与类型必须严格遵守）：",
            f"- 顶层字段：{contract.get('top_level', 'items')}",
            "- 必填字段：",
        ])
        types = contract.get("required_item_types") or {}
        for key in contract.get("required_item_keys", []):
            lines.append(f"  - {key}: {types.get(key, 'string')}")
        optional = contract.get("optional_item_types") or {}
        if optional:
            lines.append("- 可选字段（有内容才填，没有可省略；空值必须遵循字段类型）：")
            for key, kind in optional.items():
                lines.append(f"  - {key}: {kind}")
        for rule in contract.get("type_rules", []):
            lines.append(f"- {rule}")
        forbidden = contract.get("forbidden") or []
        if forbidden:
            lines.append(f"- 禁止出现的字段：{', '.join(forbidden)}")
    lines.extend([
        "",
        "SKILL.md:",
        spec.body,
    ])
    return "\n".join(lines)
