from __future__ import annotations

import io
import textwrap
import zipfile
from pathlib import Path
from typing import Dict, List, Optional
from voice_to_speach import text_modify, transcribe_audio, process_meeting_audio, task_to_list, paragraph_modify, key_points
import streamlit as st

from agents.registry import AGENT_REGISTRY, DEFAULT_AGENT_SEQUENCE
from graph import CampaignState, prepare_initial_state, run_campaign
from memory import rag
from services.audio import (
    AudioProcessingError,
    MeetingMaterials,
    normalize_transcript,
    prepare_meeting_materials,
    persist_meeting_materials,
    summarize_transcript,
)
from services.google_drive import GoogleDriveError, upload_run_to_drive
meeting_notes = ""
st.set_page_config(page_title="AI Orchestrator", layout="wide")
st.title("AI Orchestrator — маркетинговый мини-стартап")

# --- session state bootstrap -------------------------------------------------
if "latest_state" not in st.session_state:
    st.session_state.latest_state = None
if "run_id" not in st.session_state:
    st.session_state.run_id = None
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "save_to_drive" not in st.session_state:
    st.session_state.save_to_drive = False
if "drive_parent_id" not in st.session_state:
    st.session_state.drive_parent_id = ""
if "drive_last_link" not in st.session_state:
    st.session_state.drive_last_link = ""
if "notes_input" not in st.session_state:
    st.session_state.notes_input = ""
if "business_brief" not in st.session_state:
    st.session_state.business_brief = (
        "SaaS для аналитики продаж в рознице. Цель — 50 лидов в месяц в Румынии и Молдове."
    )
if "manual_transcript" not in st.session_state:
    st.session_state.manual_transcript = ""
if "transcript_summary" not in st.session_state:
    st.session_state.transcript_summary = ""
if "cached_meeting_materials" not in st.session_state:
    st.session_state.cached_meeting_materials: Optional[MeetingMaterials] = None
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes: Optional[bytes] = None
if "audio_filename" not in st.session_state:
    st.session_state.audio_filename: Optional[str] = None
if "agents_for_run" not in st.session_state:
    st.session_state.agents_for_run = list(DEFAULT_AGENT_SEQUENCE)
if "agents_for_summary" not in st.session_state:
    st.session_state.agents_for_summary = list(DEFAULT_AGENT_SEQUENCE)
if "project_title_input" not in st.session_state:
    st.session_state.project_title_input = "Retail Analytics SaaS"
if "model_name_input" not in st.session_state:
    st.session_state.model_name_input = ""

progress_placeholder = st.empty()
status_placeholder = st.empty()

# --- sidebar controls --------------------------------------------------------
with st.sidebar:
    st.subheader("Параметры кампании")
    project_title = st.text_input(
        "Название кампании",
        key="project_title_input",
    ).strip()
    model_name = st.text_input(
        "Модель LLM (опционально)",
        key="model_name_input",
    ).strip()
    model_override = model_name or None

    st.subheader("Материалы митинга")
    meeting_audio = st.file_uploader(
        "Аудиозапись митинга",
        type=["mp3", "wav"],
        accept_multiple_files=False,
        key="meeting_audio_file",
    )
    if meeting_audio is None:
        st.session_state.audio_bytes = None
        st.session_state.audio_filename = None
    else:
        st.audio(meeting_audio)

    existing_notes = ""

    if meeting_audio is not None:
        if st.button(
            "Транскрибировать аудио",
            disabled=st.session_state.is_running,
            key="transcribe_audio_button",
        ):
            audio_bytes = meeting_audio.getvalue()
            st.session_state.audio_bytes = audio_bytes
            st.session_state.audio_filename = meeting_audio.name or "meeting_audio.mp3"
            with st.spinner("Расшифровываем аудио…"):
                try:
                    # materials = prepare_meeting_materials(
                    #     audio_bytes,
                    #     filename=st.session_state.audio_filename,
                    #     llm_model=model_override,
                    # )
                    # WHY WHY WHY WHY
                    # materials = process_meeting_audio(meeting_audio)
                    raw_trans = process_meeting_audio(meeting_audio)
                    norm_trans = normalize_transcript(raw_trans)
                    sum_trans = summarize_transcript(norm_trans)
                    materials = MeetingMaterials(raw_transcript=raw_trans, normalized_transcript=raw_trans, summary=sum_trans)
                except AudioProcessingError as exc:
                    st.error(f"Не удалось обработать аудио: {exc}")
                    materials = None
            if materials is not None:
                st.session_state.cached_meeting_materials = materials
                transcript_text = materials.normalized_transcript or materials.raw_transcript
                transcript_text = materials.raw_transcript
                summary_text = materials.summary or transcript_text
                st.session_state.manual_transcript = transcript_text
                st.session_state.transcript_summary = summary_text
                existing_notes = transcript_text
                transcript_for_notes = transcript_text.strip()
                if transcript_for_notes:
                    if existing_notes:
                        if transcript_for_notes not in existing_notes:
                            st.session_state.notes_input = (
                                f"{existing_notes}\n\n{transcript_for_notes}"
                            )
                    else:
                        st.session_state.notes_input = transcript_for_notes
                st.success("Транскрипт готов и добавлен в заметки.")
                
    # st.markdown(existing_notes)
    st.text_area(
        "Транскрипт митинга (можно поправить)",
        value=existing_notes,
        key="manual_transcript",
        height=180,
    )
        
    st.subheader("Заметки и договорённости")
    st.text_area(
        "То, что важно сохранить для отчёта",
        
        key="notes_input",
        height=160,
    )

    st.subheader("Главный бриф")
    st.text_area(
        "Опиши продукт, аудиторию и основную цель",
        key="business_brief",
        height=160,
    )

    st.subheader("Дополнительные материалы (RAG)")
    uploaded_files = st.file_uploader(
        "Текстовые файлы (Markdown/Text)",
        accept_multiple_files=True,
        type=["txt", "md"],
        help="Будут использованы как дополнительный контекст",
        key="extra_docs_uploader",
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

    st.subheader("Агенты")
    agent_ids = list(AGENT_REGISTRY.keys())
    agent_labels = {agent_id: cfg.title for agent_id, cfg in AGENT_REGISTRY.items()}

    selected_agents_raw = st.multiselect(
        "Кто работает",
        options=agent_ids,
        format_func=lambda agent_id: agent_labels.get(agent_id, agent_id),
        key="agents_for_run",
    )
    selected_agents = [
        agent_id for agent_id in DEFAULT_AGENT_SEQUENCE if agent_id in selected_agents_raw
    ]

    filtered_summary = [
        agent_id for agent_id in st.session_state.agents_for_summary if agent_id in selected_agents
    ]
    if selected_agents and not filtered_summary:
        filtered_summary = list(selected_agents)
    if filtered_summary != st.session_state.agents_for_summary:
        st.session_state.agents_for_summary = filtered_summary

    summary_agents_raw = st.multiselect(
        "В итоговый отчёт",
        options=selected_agents,
        format_func=lambda agent_id: agent_labels.get(agent_id, agent_id),
        key="agents_for_summary",
    )
    summary_agents = [
        agent_id for agent_id in selected_agents if agent_id in summary_agents_raw
    ] or list(selected_agents)

    st.subheader("Сохранение")
    st.session_state.save_to_drive = st.checkbox(
        "Отправить артефакты в Google Drive",
        value=st.session_state.save_to_drive,
    )
    if st.session_state.save_to_drive:
        st.session_state.drive_parent_id = st.text_input(
            "ID папки (опционально)",
            value=st.session_state.drive_parent_id,
            help="Если оставить пустым, папка будет создана в корне диска",
        )

    run_button = st.button(
        "Запустить оркестрацию",
        type="primary",
        disabled=st.session_state.is_running or not selected_agents,
        key="run_workflow_button",
    )
    stop_button = st.button(
        "Остановить процесс",
        type="secondary",
        disabled=not st.session_state.is_running,
        key="stop_workflow_button",
    )

    if not selected_agents:
        st.warning("Выбери хотя бы одного агента для запуска.")

    if stop_button:
        st.session_state.stop_requested = True
        st.info("Остановка запрошена. Процесс завершится после текущего шага.")

# --- orchestration trigger ---------------------------------------------------
if run_button:
    st.session_state.stop_requested = False
    st.session_state.is_running = True
    st.session_state.drive_last_link = ""

    business_brief_text = st.session_state.business_brief.strip()
    if not business_brief_text:
        st.session_state.is_running = False
        st.warning("Заполни главный бриф перед запуском.")
        st.stop()

    notes_text = st.session_state.notes_input.strip()
    manual_transcript_text = st.session_state.manual_transcript.strip()

    attachments = dict(extra_documents)

    meeting_materials = st.session_state.cached_meeting_materials
    audio_bytes = st.session_state.audio_bytes
    audio_filename = st.session_state.audio_filename

    if meeting_materials is None and meeting_audio is not None:
        audio_bytes = meeting_audio.getvalue()
        audio_filename = meeting_audio.name or "meeting_audio.m4a"
        try:
            meeting_materials = prepare_meeting_materials(
                audio_bytes,
                filename=audio_filename,
                llm_model=model_override,
            )
        except AudioProcessingError as exc:
            st.session_state.is_running = False
            st.error(f"Не удалось обработать аудио: {exc}")
            st.stop()
        st.session_state.cached_meeting_materials = meeting_materials
        st.session_state.audio_bytes = audio_bytes
        st.session_state.audio_filename = audio_filename
        st.session_state.manual_transcript = (
            meeting_materials.normalized_transcript or meeting_materials.raw_transcript
        )
        st.session_state.transcript_summary = (
            meeting_materials.summary
            or meeting_materials.normalized_transcript
            or meeting_materials.raw_transcript
        )
        manual_transcript_text = st.session_state.manual_transcript.strip()
        if not notes_text:
            notes_text = (
                meeting_materials.summary
                or meeting_materials.normalized_transcript
                or meeting_materials.raw_transcript
            ).strip()
            st.session_state.notes_input = notes_text

    if manual_transcript_text:
        source_transcript = ""
        if meeting_materials is not None:
            source_transcript = (
                meeting_materials.normalized_transcript
                or meeting_materials.raw_transcript
                or ""
            ).strip()
        if not source_transcript or manual_transcript_text != source_transcript:
            normalized_manual = normalize_transcript(
                manual_transcript_text,
                model=model_override,
            )
            summary_manual = summarize_transcript(
                normalized_manual or manual_transcript_text,
                model=model_override,
            )
            meeting_materials = MeetingMaterials(
                raw_transcript=(
                    meeting_materials.raw_transcript
                    if meeting_materials and meeting_materials.raw_transcript
                    else manual_transcript_text
                ),
                normalized_transcript=normalized_manual or manual_transcript_text,
                summary=summary_manual or normalized_manual or manual_transcript_text,
            )
            st.session_state.cached_meeting_materials = meeting_materials
            st.session_state.transcript_summary = meeting_materials.summary

    brief_sections = [business_brief_text]
    if notes_text:
        brief_sections.append(f"Заметки митинга:\n{notes_text}")
    base_brief = "\n\n".join(brief_sections)

    meeting_summary_text = (
        st.session_state.transcript_summary.strip()
        if st.session_state.transcript_summary.strip()
        else notes_text
        or business_brief_text
    )

    initial_state = prepare_initial_state(
        base_brief,
        model=model_override,
        project_title=project_title or "Маркетинговая кампания",
        extra_documents=attachments or None,
        selected_agents=selected_agents,
        agents_for_summary=summary_agents,
        meeting_summary=meeting_summary_text,
        transcript_raw=meeting_materials.raw_transcript if meeting_materials else None,
        transcript_clean=
        meeting_materials.normalized_transcript if meeting_materials else None,
    )

    st.session_state.run_id = initial_state["run_id"]

    if meeting_materials is not None:
        meeting_materials = persist_meeting_materials(
            initial_state["run_id"],
            meeting_materials,
            audio_bytes=audio_bytes,
            audio_filename=audio_filename,
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
        st.session_state.cached_meeting_materials = meeting_materials

    total_steps = 2 + len(selected_agents)
    progress = progress_placeholder.progress(0, text="Подготовка к запуску…")

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
        progress_placeholder.empty()
        status_placeholder.empty()
        st.error(f"Ошибка при запуске оркестрации: {exc}")
        st.stop()

    progress_placeholder.empty()
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
        run_dir_path = (rag.ARTIFACT_ROOT / st.session_state.run_id).resolve()
        with st.spinner("Загружаем артефакты в Google Drive…"):
            try:
                folder_link = upload_run_to_drive(
                    st.session_state.run_id,
                    run_dir_path,
                    parent_id=st.session_state.drive_parent_id or None,
                )
            except GoogleDriveError as exc:
                st.warning(f"Не удалось загрузить артефакты в Google Drive: {exc}")
            else:
                st.session_state.drive_last_link = folder_link
                st.success(f"Артефакты сохранены в Google Drive: {folder_link}")

    st.session_state.stop_requested = False

# --- main content ------------------------------------------------------------
latest_state: CampaignState | None = st.session_state.get("latest_state")
run_id = st.session_state.get("run_id")

progress_tab, materials_tab, artifacts_tab, summary_tab = st.tabs(
    [
        "Прогресс",
        "Материалы митинга",
        "Артефакты",
        "Итоговый отчёт",
    ]
)

with progress_tab:
    st.subheader("Доска задач")
    if latest_state is None:
        st.info("Запусти процесс, чтобы увидеть прогресс агентов.")
    else:
        if latest_state.get("interrupted"):
            st.warning("Последний запуск был остановлен до завершения всех шагов.")

        board = (latest_state or {}).get("board", {})
        status_columns: Dict[str, List[tuple[str, str, str]]] = {
            "Backlog": [],
            "In Progress": [],
            "Done": [],
        }
        for task_id, task in board.items():
            status = task.get("status", "Backlog")
            status_columns.setdefault(status, []).append(
                (
                    task.get("title", task_id),
                    task.get("owner", ""),
                    task.get("notes", ""),
                )
            )

        backlog_col, doing_col, done_col = st.columns(3)

        def _render_column(container, title: str, items: List[tuple[str, str, str]]) -> None:
            container.markdown(f"**{title}**")
            if not items:
                container.caption("—")
            for name, owner, notes in items:
                container.markdown(f"{name}  _{owner}_")
                if notes:
                    snippet = textwrap.shorten(
                        notes.replace("\n", " "), width=160, placeholder="…"
                    )
                    container.caption(snippet)

        _render_column(backlog_col, "Backlog", status_columns.get("Backlog", []))
        _render_column(doing_col, "In Progress", status_columns.get("In Progress", []))
        _render_column(done_col, "Done", status_columns.get("Done", []))


with materials_tab:
    st.subheader("Саммари митинга")
    if existing_notes :
        meeting_notes, tasks_section = text_modify(existing_notes)
        meeting_notes = paragraph_modify(meeting_notes)
        meeting_notes = key_points(meeting_notes)
        st.expander("Параграфы из митинга", expanded=False).markdown(meeting_notes)
        # prepare a list of tasks out of task text (tasks_section)
        # tasks_list = task_to_list(tasks_section)
        # tasks_section = "\n".join([f"{task_content}" for task_content in tasks_list])
        # tasks_section = "Tasks:\n"+tasks_section
        # print(f"{tasks_section=}")
        # st.expander("Задачи из митинга", expanded=False).markdown(tasks_section)
        tasks_list = task_to_list(tasks_section)
        tasks_markdown = "\n\n---\n\n".join(tasks_list)  # разделим линии
        st.expander("Задачи из митинга", expanded=False).markdown(tasks_markdown)

    elif existing_notes:
        st.info("Саммари появится после завершения оркестрации.")
    else:
        st.info("После запуска здесь появится саммари и транскрипт митинга.")

    if st.session_state.notes_input.strip():
        st.markdown("**Заметки**")
        st.markdown(st.session_state.notes_input)

    if latest_state and latest_state.get("transcript_clean"):
        with st.expander("Нормализованный транскрипт"):
            st.markdown(latest_state["transcript_clean"])
    elif st.session_state.manual_transcript.strip():
        with st.expander("Транскрипт (черновик)"):
            st.markdown(st.session_state.manual_transcript)

    # if latest_state and latest_state.get("transcript_raw"):
    #     with st.expander("Черновой транскрипт из аудио"):
    #         st.markdown(latest_state["transcript_raw"])

    if latest_state and latest_state.get("audio_path"):
        st.caption(f"Исходный аудио-файл сохранён как `{latest_state['audio_path']}`")

with artifacts_tab:
    st.subheader("Артефакты кампании")
    if st.session_state.drive_last_link:
        st.info(f"Артефакты выгружены в Google Drive: {st.session_state.drive_last_link}")

    artifacts = rag.list_artifacts(run_id) if run_id else []
    run_dir_path: Optional[Path] = (rag.ARTIFACT_ROOT / run_id) if run_id else None

    if artifacts:
        for artifact in artifacts:
            with st.expander(artifact.title):
                st.markdown(artifact.path.read_text(encoding="utf-8"))
    else:
        st.caption("Артефакты появятся после выполнения оркестрации.")

    if run_dir_path and run_dir_path.exists():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run_dir_path.iterdir()):
                if path.is_file():
                    archive.write(path, arcname=path.name)
        st.download_button(
            "Скачать все файлы ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"{run_id}_artifacts.zip",
            mime="application/zip",
        )

with summary_tab:
    st.subheader("Итоговая сводка")
    if latest_state and latest_state.get("summary"):
        st.markdown(latest_state["summary"])
    elif latest_state:
        st.info("Финальная сводка ещё формируется.")
    else:
        st.info("Запусти оркестрацию, чтобы получить финальный отчёт.")
