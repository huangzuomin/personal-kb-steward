"""T6 A2: thin case-story-bank-builder executor.

Delegates to the SHARED typed pipeline (core.card_pipeline.discover_cards)
for cases only, over persisted-source eligibility collected from the provided
vault index. No alternate writer, no second identity authority, no direct
model calls: the provider is injectable through context["providers"] and
otherwise defaults to core.llm.call_chat_completion inside the generator.

Expected context: {"config", "vault_index", "use_llm", "run_id"?, "providers"?}.
Returns a typed executor envelope whose "planned_pages" are ordinary plan page
specs bound through the existing save-plan -> review -> apply flow.
"""
from __future__ import annotations

from typing import Any


def execute(context: dict[str, Any]) -> dict[str, Any]:
    from core.card_pipeline import discover_cards

    cfg = context["config"]
    index = context["vault_index"]
    discovery = discover_cards(
        index, cfg,
        run_id=str(context.get("run_id") or "case-story-bank-builder"),
        use_llm=bool(context.get("use_llm", True)),
        kinds=("case",),
        providers=context.get("providers"),
        skill="case-story-bank-builder")
    pages = [dict(page, target=page["rel_path"])
             for page in discovery["planned_pages"]]
    inputs = sorted({rel for page in pages for rel in page.get("sources", [])})
    return {
        "skill": "case-story-bank-builder",
        "planned_pages": pages,
        "inputs": inputs,
        "processed": 0,  # review gate owns promotion; never self-approve
        "issues": discovery["issues"],
        "stages": discovery["stages"],
    }
