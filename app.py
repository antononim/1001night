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
st.title("AI Orchestrator — marketing mini-startup")

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
        "SaaS for retail sales analytics. Goal — 50 leads per month in Romania and Moldova."
    )
if "manual_transcript" not in st.session_state:
    st.session_state.manual_transcript = ""
if "transcript_summary" not in st.session_state:
    st.session_state.transcript_summary = ""
if "cached_meeting_materials" not in st.session_state:
    # st.session_state.cached_meeting_materials: Optional[MeetingMaterials] = None
    st.session_state.cached_meeting_materials = None
if "audio_bytes" not in st.session_state:
    # st.session_state.audio_bytes: Optional[bytes] = None
    st.session_state.audio_bytes = None
if "audio_filename" not in st.session_state:
    # st.session_state.audio_filename: Optional[str] = None
    st.session_state.audio_filename = None
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
    st.subheader("Campaign parameters")
    project_title = st.text_input(
        "Campaign title",
        key="project_title_input",
    ).strip()
    model_name = st.text_input(
        "LLM model (optional)",
        key="model_name_input",
    ).strip()
    model_override = model_name or None

    st.subheader("Meeting materials")
    meeting_audio = st.file_uploader(
        "Meeting audio recording",
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
            "Transcribe audio",
            disabled=st.session_state.is_running,
            key="transcribe_audio_button",
        ):
            audio_bytes = meeting_audio.getvalue()
            st.session_state.audio_bytes = audio_bytes
            st.session_state.audio_filename = meeting_audio.name or "meeting_audio.mp3"
            with st.spinner("Transcribing audio…"):
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
                    st.error(f"Failed to process audio: {exc}")
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
                st.success("Transcript is ready and added to notes.")
                
    # st.markdown(existing_notes)
    st.text_area(
        "Meeting transcript (editable)",
        value=existing_notes,
        key="manual_transcript",
        height=180,
    )
        
    st.subheader("Notes and agreements")
    st.text_area(
        "ТImportant information to keep for the report",
        
        key="notes_input",
        height=160,
    )

    st.subheader("Main brief")
    st.text_area(
        "Describe the product, audience, and main goal",
        key="business_brief",
        height=160,
    )

    st.subheader("Additional materials (RAG)")
    uploaded_files = st.file_uploader(
        "Text files (Markdown/Text)",
        accept_multiple_files=True,
        type=["txt", "md"],
        help="Will be used as additional context",
        key="extra_docs_uploader",
    )

    extra_documents: Dict[str, str] = {}
    if uploaded_files:
        for file in uploaded_files:
            try:
                content = file.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.warning(f"Could not read file {file.name}. Use UTF-8 encoding.")
                continue
            extra_documents[file.name] = content

    st.subheader("Agents")
    agent_ids = list(AGENT_REGISTRY.keys())
    agent_labels = {agent_id: cfg.title for agent_id, cfg in AGENT_REGISTRY.items()}

    selected_agents_raw = st.multiselect(
        "Which agents work",
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
        "In the final report",
        options=selected_agents,
        format_func=lambda agent_id: agent_labels.get(agent_id, agent_id),
        key="agents_for_summary",
    )
    summary_agents = [
        agent_id for agent_id in selected_agents if agent_id in summary_agents_raw
    ] or list(selected_agents)

    st.subheader("Saving")
    st.session_state.save_to_drive = st.checkbox(
        "Send artifacts to Google Drive",
        value=st.session_state.save_to_drive,
    )
    if st.session_state.save_to_drive:
        st.session_state.drive_parent_id = st.text_input(
            "Folder ID (optional)",
            value=st.session_state.drive_parent_id,
            help="If left empty, folder will be created in the root of the drive",
        )

    run_button = st.button(
        "Start orchestration",
        type="primary",
        disabled=st.session_state.is_running or not selected_agents,
        key="run_workflow_button",
    )
    stop_button = st.button(
        "Stop process",
        type="secondary",
        disabled=not st.session_state.is_running,
        key="stop_workflow_button",
    )

    if not selected_agents:
        st.warning("Select at least one agent to start.")

    if stop_button:
        st.session_state.stop_requested = True
        st.info("Stop requested. Process will finish after current step.")

# --- orchestration trigger ---------------------------------------------------
if run_button:
    st.session_state.stop_requested = False
    st.session_state.is_running = True
    st.session_state.drive_last_link = ""

    business_brief_text = st.session_state.business_brief.strip()
    if not business_brief_text:
        st.session_state.is_running = False
        st.warning("Fill in the main brief before starting.")
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
            st.error(f"Failed to process audio: {exc}")
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
        brief_sections.append(f"Meeting notes:\n{notes_text}")
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
        project_title=project_title or "Marketing campaign",
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
    progress = progress_placeholder.progress(0, text="Preparing to start…")

    step_labels = {
        "manager_plan": "Manager — planning",
        "manager_summary": "Manager — final assembly",
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
        status_placeholder.info(f"Current step: {label}")
        st.session_state.latest_state = current_state

    try:
        final_state = run_campaign(
            initial_state,
            stop_signal=lambda: st.session_state.stop_requested,
            on_step=_handle_step,
        )
    except Exception as exc:  # pragma: no cover - surface errors in UI
        st.session_state.is_running = False
        progress_placeholder.empty()
        status_placeholder.empty()
        st.error(f"Error running orchestration: {exc}")
        st.stop()

    progress_placeholder.empty()
    status_placeholder.empty()
    st.session_state.is_running = False
    st.session_state.latest_state = final_state

    if final_state.get("interrupted"):
        st.warning("Process stopped. Partial results are available.")
    else:
        st.success("Done! Campaign is assembled.")

    if (
        st.session_state.save_to_drive
        and not final_state.get("interrupted")
        and st.session_state.run_id
    ):
        run_dir_path = (rag.ARTIFACT_ROOT / st.session_state.run_id).resolve()
        with st.spinner("Uploading artifacts to Google Drive…"):
            try:
                folder_link = upload_run_to_drive(
                    st.session_state.run_id,
                    run_dir_path,
                    parent_id=st.session_state.drive_parent_id or None,
                )
            except GoogleDriveError as exc:
                st.warning(f"Failed to upload artifacts to Google Drive: {exc}")
            else:
                st.session_state.drive_last_link = folder_link
                st.success(f"Artifacts saved to Google Drive: {folder_link}")

    st.session_state.stop_requested = False

# --- main content ------------------------------------------------------------
latest_state: CampaignState | None = st.session_state.get("latest_state")
run_id = st.session_state.get("run_id")

progress_tab, materials_tab, artifacts_tab, summary_tab = st.tabs(
    [
        "Progress",
        "Meeting materials",
        "Artifacts",
        "Final report",
    ]
)

with progress_tab:
    st.subheader("Task board")
    if latest_state is None:
        st.info("Start the process to see agents' progress.")
    else:
        if latest_state.get("interrupted"):
            st.warning("The last run was stopped before completing all steps.")

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
    st.subheader("Meeting summary")
    if existing_notes :
        meeting_notes, tasks_section = text_modify(existing_notes)
        meeting_notes = paragraph_modify(meeting_notes)
        meeting_notes = key_points(meeting_notes)
        st.expander("Meeting paragraphs", expanded=False).markdown(meeting_notes)
        # prepare a list of tasks out of task text (tasks_section)
        # tasks_list = task_to_list(tasks_section)
        # tasks_section = "\n".join([f"{task_content}" for task_content in tasks_list])
        # tasks_section = "Tasks:\n"+tasks_section
        # print(f"{tasks_section=}")
        # st.expander("Tasks from meeting", expanded=False).markdown(tasks_section)
        tasks_list = task_to_list(tasks_section)
        tasks_markdown = "\n\n---\n\n".join(tasks_list)  # Add separator lines
        st.expander("Tasks from meeting", expanded=False).markdown(tasks_markdown)

    elif existing_notes:
        st.info("Summary will appear after orchestration completes.")
    else:
        st.info("Summary and transcript will appear here after starting.")

    if st.session_state.notes_input.strip():
        st.markdown("**Notes**")
        st.markdown(st.session_state.notes_input)

    if latest_state and latest_state.get("transcript_clean"):
        with st.expander("Normalized transcript"):
            st.markdown(latest_state["transcript_clean"])
    elif st.session_state.manual_transcript.strip():
        with st.expander("Transcript (draft)"):
            st.markdown(st.session_state.manual_transcript)

    # if latest_state and latest_state.get("transcript_raw"):
    #     with st.expander("Raw transcript from audio"):
    #         st.markdown(latest_state["transcript_raw"])

    if latest_state and latest_state.get("audio_path"):
        st.caption(f"Original audio file saved as `{latest_state['audio_path']}`")

with artifacts_tab:
    st.subheader("Campaign artifacts")
    if st.session_state.drive_last_link:
        st.info(f"Artifacts uploaded to Google Drive: {st.session_state.drive_last_link}")

    artifacts = rag.list_artifacts(run_id) if run_id else []
    run_dir_path: Optional[Path] = (rag.ARTIFACT_ROOT / run_id) if run_id else None

    if artifacts:
        for artifact in artifacts:
            with st.expander(artifact.title):
                st.markdown(artifact.path.read_text(encoding="utf-8"))
    else:
        st.caption("Artifacts will appear after orchestration runs.")

    if run_dir_path and run_dir_path.exists():
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run_dir_path.iterdir()):
                if path.is_file():
                    archive.write(path, arcname=path.name)
        st.download_button(
            "Download all files as ZIP",
            data=zip_buffer.getvalue(),
            file_name=f"{run_id}_artifacts.zip",
            mime="application/zip",
        )

with summary_tab:
    st.subheader("Final summary")
    if latest_state and latest_state.get("summary"):
        st.markdown(latest_state["summary"])
    elif latest_state:
        st.info("Final summary is still being generated.")
    else:
        st.info("Run orchestration to get the final report.")
