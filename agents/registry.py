# from __future__ import annotations

# from dataclasses import dataclass
# from typing import Any, Callable, Dict, List

# from agents import analyst, copywriter, ideator, tehnician, finance

# AgentHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


# @dataclass(frozen=True)
# class AgentConfig:
#     """Описание агентской роли, доступной в оркестрации."""

#     id: str
#     title: str
#     owner: str
#     description: str
#     handler: AgentHandler
#     result_key: str
#     default_selected: bool = True
#     default_in_summary: bool = True


# _AGENT_CONFIGS: List[AgentConfig] = [
#     AgentConfig(
#         id="analyst_icp",
#         title="Аналитик (ICP)",
#         owner="Analyst",
#         description="Исследует рынок и формирует портрет целевой аудитории.",
#         handler=analyst.icp,
#         result_key="icp",
#     ),
#     AgentConfig(
#         id="ideator_concepts",
#         title="Креативщик",
#         owner="Ideator",
#         description="Готовит креативные концепции кампании и сообщения для коммуникаций.",
#         handler=ideator.concepts,
#         result_key="concepts",
#     ),
#     AgentConfig(
#         id="copywriter_texts",
#         title="Копирайтер",
#         owner="Copywriter",
#         description="Создает тексты для промо-материалов с учётом выбранной концепции.",
#         handler=copywriter.texts,
#         result_key="copy",
#     ),
#     AgentConfig(
#         id="technician_blueprint",
#         title="Технарь",
#         owner="Technician",
#         description="Разрабатывает технический план реализации кампании.",
#         handler=tehnician.blueprint,
#         result_key="tech_plan",
#     ),
#     AgentConfig(
#         id="finance_assessment",
#         title="Финансист",
#         owner="Finance",
#         description="Проводит финансовый анализ и оценку кампании.",
#         handler=finance.assessment,
#         result_key="finance",
#     ),
# ]

# AGENT_REGISTRY: Dict[str, AgentConfig] = {cfg.id: cfg for cfg in _AGENT_CONFIGS}
# DEFAULT_AGENT_SEQUENCE: List[str] = [cfg.id for cfg in _AGENT_CONFIGS if cfg.default_selected]
# DEFAULT_SUMMARY_AGENTS: List[str] = [
#     cfg.id for cfg in _AGENT_CONFIGS if cfg.default_in_summary
# ]


# __all__ = [
#     "AgentConfig",
#     "AgentHandler",
#     "AGENT_REGISTRY",
#     "DEFAULT_AGENT_SEQUENCE",
#     "DEFAULT_SUMMARY_AGENTS",
# ]
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from agents import analyst, copywriter, finance, ideator, technician

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
        title="Analyst (ICP)",
        owner="Analyst",
        description="Исследует рынок и формирует портрет целевой аудитории.",
        handler=analyst.icp,
        result_key="icp",
    ),
    AgentConfig(
        id="ideator_concepts",
        title="Ideator",
        owner="Ideator",
        description="Готовит креативные концепции кампании и сообщения для коммуникаций.",
        handler=ideator.concepts,
        result_key="concepts",
    ),
    AgentConfig(
        id="finance_assessment",
        title="Finance assistant",
        owner="CFO",
        description="Оценивает бюджет, риски и финансовые сценарии проекта.",
        handler=finance.assessment,
        result_key="finance",
    ),
    AgentConfig(
        id="technician_blueprint",
        title="Technician",
        owner="CTO",
        description="Определяет архитектуру, стек и план реализации продукта.",
        handler=technician.blueprint,
        result_key="tech_plan",
    ),
    AgentConfig(
        id="copywriter_texts",
        title="Copywriter",
        owner="Copywriter",
        description="Создает тексты для промо-материалов с учётом выбранной концепции.",
        handler=copywriter.texts,
        result_key="copy",
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