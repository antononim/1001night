from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from agents import analyst, copywriter, ideator
from agents import finance, cto

AgentHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class AgentConfig:
    """Описание агентской роли, доступной в оркестрации."""

    id: str
    title: str
    owner: str
    description: str
    handler: AgentHandler
    result_key: str
    default_selected: bool = True
    default_in_summary: bool = True


_AGENT_CONFIGS: List[AgentConfig] = [
    AgentConfig(
        id="analyst_icp",
        title="ICP Analyst",
        owner="Analyst",
        description="Исследует рынок и формирует портрет целевой аудитории.",
        handler=analyst.icp,
        result_key="icp",
    ),
    AgentConfig(
        id="ideator_concepts",
        title="Creative Strategist",
        owner="Ideator",
        description="Готовит креативные концепции кампании и сообщения для коммуникаций.",
        handler=ideator.concepts,
        result_key="concepts",
    ),
    AgentConfig(
        id="copywriter_texts",
        title="Copywriter",
        owner="Copywriter",
        description="Создает тексты для промо-материалов с учётом выбранной концепции.",
        handler=copywriter.texts,
        result_key="copy",
    ),
    AgentConfig(
        id="finance_analysis",
        title="Financial Analyst",
        owner="CFO",
        description="Оценивает финансовую реализуемость идеи, анализирует сценарии и риски.",
        handler=finance.analysis,
        result_key="finance",
    ),
    AgentConfig(
        id="cto_roadmap",
        title="Techical Assistant",
        owner="CTO",
        description="Формирует техническое видение и план реализации продукта и кампании.",
        handler=cto.roadmap,
        result_key="technology",
    ),
]

AGENT_REGISTRY: Dict[str, AgentConfig] = {cfg.id: cfg for cfg in _AGENT_CONFIGS}
DEFAULT_AGENT_SEQUENCE: List[str] = [cfg.id for cfg in _AGENT_CONFIGS if cfg.default_selected]
DEFAULT_SUMMARY_AGENTS: List[str] = [
    cfg.id for cfg in _AGENT_CONFIGS if cfg.default_in_summary
]


__all__ = [
    "AgentConfig",
    "AgentHandler",
    "AGENT_REGISTRY",
    "DEFAULT_AGENT_SEQUENCE",
    "DEFAULT_SUMMARY_AGENTS",
]
