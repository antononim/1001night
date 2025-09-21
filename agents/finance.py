from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from agents._llm import chat
from memory.rag import get_context, save_artifact

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPT_TEXT = (BASE_DIR / "prompts" / "finance.md").read_text(encoding="utf-8")


def assessment(state: Dict[str, Any]) -> Dict[str, Any]:
    brief: str = state["brief"]
    run_id: str = state["run_id"]
    icp: str = state.get("icp", "")
    concepts: str = state.get("concepts", "")
    model: str | None = state.get("model")

    context_query = "\n\n".join(filter(None, [brief, icp, concepts])) or brief
    context = get_context(run_id, query=context_query, k=5)

    response = chat(
        [
            {"role": "system", "content": PROMPT_TEXT},
            {
                "role": "user",
                "content": (
                    f"Бриф:\n{brief}\n\nICP:\n{icp}\n\n"
                    f"Концепции:\n{concepts}\n\nКонтекст из памяти:\n{context}\n\n"
                    "Сформируй финансовый анализ по пунктам."
                ),
            },
        ],
        model=model,
    )

    artifact = save_artifact(run_id, "finance_assessment.md", response)

    board = deepcopy(state.get("board", {}))
    board.setdefault("finance_assessment", {})
    board["finance_assessment"].update({"status": "Done", "notes": response})

    artifacts = list(state.get("artifacts", []))
    artifacts.append(str(artifact))

    return {
        "finance": response,
        "artifacts": artifacts,
        "board": board,
    }


__all__ = ["assessment"]