from __future__ import annotations

import io
import textwrap
from turtle import pd
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from voice_to_speach import text_modify, transcribe_audio
import streamlit as st
from voice_to_speach import process_meeting_audio

from agents._llm import chat
from agents.registry import AGENT_REGISTRY, DEFAULT_AGENT_SEQUENCE
from graph import CampaignState, prepare_initial_state, run_campaign
from memory import rag
from services.audio import (
    AudioProcessingError,
    MeetingMaterials,
    prepare_meeting_materials,
    persist_meeting_materials,
)
from services.google_drive import GoogleDriveError, upload_run_to_drive
meeting_notes = ""
st.set_page_config(page_title="AI Orchestrator", layout="wide")
st.title("AI Orchestrator — маркетинговый мини-стартап")

if "latest_state" not in st.session_state:
    st.session_state.latest_state = None
if "run_id" not in st.session_state:
    st.session_state.run_id = None
if "selected_agents" not in st.session_state:
    st.session_state.selected_agents = list(DEFAULT_AGENT_SEQUENCE)
if "summary_agents" not in st.session_state:
    st.session_state.summary_agents = list(DEFAULT_AGENT_SEQUENCE)
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "meeting_materials" not in st.session_state:
    st.session_state.meeting_materials = None
if "save_to_drive" not in st.session_state:
    st.session_state.save_to_drive = False
if "drive_parent_id" not in st.session_state:
    st.session_state.drive_parent_id = ""
if "drive_last_link" not in st.session_state:
    st.session_state.drive_last_link = ""

col_input, col_view = st.columns([1, 2])

with col_input:
    st.header("Материалы")
    meeting_audio = st.file_uploader(
        "Аудиозапись митинга",
        type=["mp3", "wav"],
        accept_multiple_files=False,
    )
    if meeting_audio is not None:
        st.audio(meeting_audio)

    if st.button("Проанализировать", type="primary"):
        if not meeting_audio:
            st.warning("Загрузите запись встречи, чтобы запустить анализ.")
        else:
            try:
                with st.spinner("Анализируем запись встречи..."):
                    meeting_notes = process_meeting_audio(meeting_audio)
            except Exception as exc: 
                st.error(f"Ошибка при анализе записи встречи: {exc}")
            else:
                st.success("Анализ завершен!")
                st.subheader("Заметки по встрече")
                # st.markdown(meeting_notes)


    default_brief = "SaaS для аналитики продаж в рознице. Цель — 50 лидов в месяц в Румынии и Молдове."
    brief = st.text_area(
        "Дополнительные заметки или цели",
        value=default_brief,
        height=220,
    )

    uploaded_files = st.file_uploader(
        "Текстовые материалы (Markdown/Text)",
        accept_multiple_files=True,
        type=["txt", "md"],
        help="Эти файлы будут использованы в RAG контексте",
    )

    extra_documents: Dict[str, str] = {}
    if uploaded_files:
        for file in uploaded_files:
            try:
                content = file.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.warning(f"Не удалось прочитать файл {file.name}. Используйте UTF-8.")
                continue
            extra_documents[file.name] = content

    st.subheader("Настройки кампании")
    project_title = st.text_input("Название кампании", value="Retail Analytics SaaS")
    model_name = st.text_input("Модель LLM (опционально)", value="")

    st.subheader("Агенты")
    agent_ids = list(AGENT_REGISTRY.keys())
    agent_labels = {agent_id: cfg.title for agent_id, cfg in AGENT_REGISTRY.items()}

    selected_agents_raw = st.multiselect(
        "Выбери агентов для запуска",
        options=agent_ids,
        default=st.session_state.selected_agents,
        format_func=lambda agent_id: agent_labels.get(agent_id, agent_id),
    )
    selected_agents = [
        agent_id for agent_id in DEFAULT_AGENT_SEQUENCE if agent_id in selected_agents_raw
    ]
    if selected_agents != st.session_state.selected_agents:
        st.session_state.selected_agents = selected_agents

    if not selected_agents:
        st.warning("Выбери хотя бы одного агента, чтобы запустить процесс.")

    summary_agents_raw = st.multiselect(
        "Добавить в итоговую сводку",
        options=selected_agents,
        default=[
            agent_id
            for agent_id in st.session_state.summary_agents
            if agent_id in selected_agents
        ],
        format_func=lambda agent_id: agent_labels.get(agent_id, agent_id),
    )
    summary_agents = [
        agent_id for agent_id in selected_agents if agent_id in summary_agents_raw
    ] or list(selected_agents)
    if summary_agents != st.session_state.summary_agents:
        st.session_state.summary_agents = summary_agents

    st.subheader("Сохранение")
    save_to_drive = st.checkbox(
        "Отправить артефакты в Google Drive",
        value=st.session_state.save_to_drive,
    )
    st.session_state.save_to_drive = save_to_drive
    drive_parent_id = ""
    if save_to_drive:
        drive_parent_id = st.text_input(
            "ID папки в Google Drive (опционально)",
            value=st.session_state.drive_parent_id,
            help="Если оставить пустым, будет создана папка в корне диска.",
        )
        st.session_state.drive_parent_id = drive_parent_id

    run_button = st.button(
        "Запустить оркестрацию",
        type="primary",
        disabled=st.session_state.is_running or not selected_agents,
    )
    stop_button = st.button(
        "Остановить процесс",
        type="secondary",
        disabled=not st.session_state.is_running,
    )

    if stop_button:
        st.session_state.stop_requested = True
        st.info("Остановка запрошена. Процесс завершится после текущего шага.")

    if run_button:
        st.session_state.stop_requested = False
        st.session_state.is_running = True
        attachments = dict(extra_documents)

        meeting_materials: Optional[MeetingMaterials] = None
        audio_bytes: Optional[bytes] = None

        if meeting_audio is not None:
            audio_bytes = meeting_audio.getvalue()
            try:
                meeting_materials = prepare_meeting_materials(
                    audio_bytes,
                    filename=meeting_audio.name or "meeting_audio.m4a",
                    llm_model=model_name.strip() or None,
                )
            except AudioProcessingError as exc:
                st.session_state.is_running = False
                st.error(f"Не удалось обработать аудио: {exc}")
                st.stop()

        manual_brief = brief.strip()
        base_brief = ""
        meeting_summary_text = ""

        if meeting_materials:
            meeting_summary_text = meeting_materials.summary or ""
            base_brief = meeting_summary_text or meeting_materials.normalized_transcript
            if manual_brief:
                base_brief += "\n\nДополнительные заметки:\n" + manual_brief
        else:
            base_brief = manual_brief
            meeting_summary_text = manual_brief

        if not base_brief:
            st.session_state.is_running = False
            st.warning("Загрузите аудио митинга или заполните заметки, чтобы сформировать бриф.")
            st.stop()

        initial_state = prepare_initial_state(
            base_brief,
            model=model_name.strip() or None,
            project_title=project_title.strip() or "Маркетинговая кампания",
            extra_documents=attachments or None,
            selected_agents=selected_agents,
            agents_for_summary=summary_agents,
            meeting_summary=meeting_summary_text,
            transcript_raw=meeting_materials.raw_transcript if meeting_materials else None,
            transcript_clean=meeting_materials.normalized_transcript if meeting_materials else None,
        )

        st.session_state.run_id = initial_state["run_id"]

        if meeting_materials is not None:
            meeting_materials = persist_meeting_materials(
                initial_state["run_id"],
                meeting_materials,
                audio_bytes=audio_bytes,
                audio_filename=meeting_audio.name if meeting_audio else None,
            )
            artifacts = list(initial_state.get("artifacts", []))
            for path in (
                meeting_materials.raw_artifact,
                meeting_materials.normalized_artifact,
                meeting_materials.summary_artifact,
            ):
                if path:
                    artifacts.append(str(path))
            initial_state["artifacts"] = artifacts
            if meeting_materials.audio_path:
                initial_state["audio_path"] = str(meeting_materials.audio_path)
            st.session_state.meeting_materials = meeting_materials
        else:
            st.session_state.meeting_materials = None

        total_steps = 2 + len(selected_agents)
        progress = st.progress(0, text="Подготовка к запуску…")
        status_placeholder = st.empty()

        step_labels = {
            "manager_plan": "Менеджер — планирование",
            "manager_summary": "Менеджер — финальная сборка",
        }
        for agent_id in selected_agents:
            step_labels[agent_id] = agent_labels.get(agent_id, agent_id)

        progress_state = {"done": 0}

        def _handle_step(step_id: str, current_state: CampaignState) -> None:
            progress_state["done"] += 1
            completed = progress_state["done"]
            label = step_labels.get(step_id, step_id)
            progress.progress(
                completed / max(total_steps, 1),
                text=f"{completed}/{total_steps} · {label}",
            )
            status_placeholder.info(f"Текущий шаг: {label}")
            st.session_state.latest_state = current_state

        try:
            final_state = run_campaign(
                initial_state,
                stop_signal=lambda: st.session_state.stop_requested,
                on_step=_handle_step,
            )
        except Exception as exc:  # pragma: no cover - surface errors в UI
            st.session_state.is_running = False
            progress.empty()
            status_placeholder.empty()
            st.error(f"Ошибка при запуске оркестрации: {exc}")
            st.stop()

        progress.empty()
        status_placeholder.empty()
        st.session_state.is_running = False
        st.session_state.latest_state = final_state

        if final_state.get("interrupted"):
            st.warning("Процесс остановлен. Доступны промежуточные результаты.")
        else:
            st.success("Готово! Кампания собрана.")

        if (
            st.session_state.save_to_drive
            and not final_state.get("interrupted")
            and st.session_state.run_id
        ):
            run_dir = (rag.ARTIFACT_ROOT / st.session_state.run_id).resolve()
            with st.spinner("Загружаем артефакты в Google Drive…"):
                try:
                    folder_link = upload_run_to_drive(
                        st.session_state.run_id,
                        run_dir,
                        parent_id=st.session_state.drive_parent_id or None,
                    )
                except GoogleDriveError as exc:
                    st.warning(f"Не удалось загрузить артефакты в Google Drive: {exc}")
                else:
                    st.session_state.drive_last_link = folder_link
                    st.success(f"Артефакты сохранены в Google Drive: {folder_link}")

        st.session_state.stop_requested = False

with col_view:
    # st.header("Voice analysing results")
    with open("example.txt", "r", encoding="utf-8") as f:
        meeting_notes = f.read()
        meeting_notes, tasks_notes = text_modify(meeting_notes)
    if not meeting_notes:
        st.info("После анализа записи встречи здесь появятся заметки.")
    else:
        st.header("Результаты анализа записи встречи")
        with st.expander("Показать заметки по встрече", expanded=True):
            st.markdown(meeting_notes)
        with st.expander("Показать задачи по встрече", expanded=False):
            st.markdown(tasks_notes)
    
    st.header("Прогресс")
    latest_state: CampaignState | None = st.session_state.get("latest_state")
    board = (latest_state or {}).get("board", {})

    if latest_state and latest_state.get("interrupted"):
        st.warning("Последний запуск был остановлен до завершения всех шагов.")

    status_columns = {"Backlog": [], "In Progress": [], "Done": [], "Stopped": []}
    for task_id, task in board.items():
        status = task.get("status", "Backlog")
        if status not in status_columns:
            status_columns[status] = []
        status_columns[status].append((task.get("title", task_id), task.get("owner", ""), task.get("notes", "")))

    backlog_col, doing_col, done_col = st.columns(3)

    def _render_column(container, title: str, items: List[tuple[str, str, str]]) -> None:
        container.subheader(title)
        if not items:
            container.caption("—")
        for name, owner, notes in items:
            container.markdown(f"**{name}**  _{owner}_")
            if notes:
                snippet = textwrap.shorten(notes.replace("\n", " "), width=160, placeholder="…")
                container.caption(snippet)

    _render_column(backlog_col, "Backlog", status_columns.get("Backlog", []))
    _render_column(doing_col, "Doing", status_columns.get("In Progress", []))
    _render_column(done_col, "Done", status_columns.get("Done", []))
    if status_columns.get("Stopped"):
        st.subheader("Остановлено")
        for name, owner, notes in status_columns["Stopped"]:
            st.markdown(f"**{name}**  _{owner}_ (остановлено)")

    if latest_state and latest_state.get("meeting_summary"):
        st.header("Саммари митинга")
        st.markdown(latest_state["meeting_summary"])

    if latest_state and latest_state.get("transcript_clean"):
        with st.expander("Нормализованный транскрипт"):
            st.markdown(latest_state["transcript_clean"])

    if latest_state and latest_state.get("transcript_raw"):
        with st.expander("Черновой транскрипт"):
            st.markdown(latest_state["transcript_raw"])

    if latest_state and latest_state.get("audio_path"):
        st.caption(f"Исходный аудиофайл: `{latest_state['audio_path']}`")

    if st.session_state.drive_last_link:
        st.info(f"Артефакты выгружены в Google Drive: {st.session_state.drive_last_link}")

    st.header("Артефакты")
    run_id = st.session_state.get("run_id")
    artifacts = rag.list_artifacts(run_id) if run_id else []
    run_dir = (rag.ARTIFACT_ROOT / run_id) if run_id else None

    for artifact in artifacts:
        with st.expander(artifact.title):
            st.markdown(artifact.path.read_text(encoding="utf-8"))

    if run_dir and run_dir.exists():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run_dir.iterdir()):
                if path.is_file():
                    archive.write(path, arcname=path.name)
        st.download_button(
            "Скачать ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"{run_id}_artifacts.zip",
            mime="application/zip",
        )

    if latest_state and latest_state.get("summary"):
        st.header("Итоговая сводка")
        st.markdown(latest_state["summary"])

    if not latest_state:
        st.info("Запусти процесс, чтобы увидеть результаты.")
