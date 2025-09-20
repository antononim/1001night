from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from agents._llm import chat
from memory.rag import get_context, save_artifact

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_TEXT = (BASE_DIR / "prompts" / "tech.md").read_text(encoding="utf-8")


def roadmap(state: Dict[str, Any]) -> Dict[str, Any]:
    brief: str = state["brief"]
    run_id: str = state["run_id"]
    plan = state.get("plan", "")
    meeting_summary = state.get("meeting_summary", "")
    model: str | None = state.get("model")

    context = get_context(run_id, query=plan or brief, k=5)

    response = chat(
        [
            {"role": "system", "content": PROMPT_TEXT},
            {
                "role": "user",
                "content": (
                    f"Бриф:\n{brief}\n\n"
                    f"План кампании:\n{plan}\n\n"
                    f"Саммари митинга:\n{meeting_summary}\n\n"
                    f"Контекст из памяти:\n{context}"
                ),
            },
        ],
        model=model,
    )

    artifact = save_artifact(run_id, "tech_roadmap.md", response)

    board = deepcopy(state.get("board", {}))
    board.setdefault("tech_roadmap", {})
    board["tech_roadmap"].update({"status": "Done", "notes": response})

    artifacts = list(state.get("artifacts", []))
    artifacts.append(str(artifact))

    return {
        "technology": response,
        "artifacts": artifacts,
        "board": board,
    }


__all__ = ["roadmap"]
