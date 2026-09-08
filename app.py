from __future__ import annotations

import hashlib
import html
import uuid

import streamlit as st

from src.generation import LocalLLMGenerator
from src.parsers import DocumentParseError
from src.service import RagService


st.set_page_config(page_title="Acme Retail Knowledge Chat", page_icon="🛍️", layout="wide")


THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.acme-header {
    display: flex;
    align-items: center;
    gap: 0.9rem;
    padding: 1.15rem 1.5rem;
    margin-bottom: 1.4rem;
    border-radius: 14px;
    background: linear-gradient(135deg, #4338CA 0%, #4F46E5 55%, #6366F1 100%);
    color: #FFFFFF;
}
.acme-header__mark {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255, 255, 255, 0.16);
    border-radius: 10px;
}
.acme-header__mark svg { width: 24px; height: 24px; color: #FFFFFF; }
.acme-header__title {
    font-size: 1.45rem;
    font-weight: 700;
    margin: 0;
    line-height: 1.25;
    color: #FFFFFF;
}
.acme-header__subtitle {
    font-size: 0.9rem;
    margin: 0.2rem 0 0;
    color: rgba(255, 255, 255, 0.88);
}

section[data-testid="stSidebar"] {
    border-right: 1px solid #E5E7EB;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    font-weight: 600;
    color: #1F2937;
}

.acme-citation-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.35rem 0 0.5rem;
}
.acme-citation-pill {
    display: inline-flex;
    align-items: center;
    padding: 0.22rem 0.65rem;
    border-radius: 999px;
    background: #EEF2FF;
    color: #4338CA;
    font-size: 0.78rem;
    font-weight: 500;
    border: 1px solid #E0E7FF;
    white-space: nowrap;
}

.acme-confidence-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.22rem 0.65rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin: 0.35rem 0 0.5rem;
    border: 1px solid transparent;
}
.acme-confidence-badge--high {
    background: #ECFDF5;
    color: #047857;
    border-color: #A7F3D0;
}
.acme-confidence-badge--medium {
    background: #FFFBEB;
    color: #B45309;
    border-color: #FDE68A;
}
.acme-confidence-badge--low {
    background: #FEF2F2;
    color: #B91C1C;
    border-color: #FECACA;
}

.stButton > button {
    border-radius: 8px;
    font-weight: 600;
}

[data-testid="stChatMessage"] {
    border-radius: 12px;
}

[data-testid="stMetricValue"] {
    color: #4338CA;
}
"""

HEADER_HTML = """
<div class="acme-header">
  <div class="acme-header__mark">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"></path>
      <path d="M3 6h18"></path>
      <path d="M16 10a4 4 0 0 1-8 0"></path>
    </svg>
  </div>
  <div>
    <p class="acme-header__title">Acme Retail Knowledge Chat</p>
    <p class="acme-header__subtitle">Ask questions across uploaded Excel, CSV, and PowerPoint documents. Answers are limited to indexed evidence.</p>
  </div>
</div>
"""


def inject_theme() -> None:
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(HEADER_HTML, unsafe_allow_html=True)


def render_citations(citations: list[str]) -> None:
    """Render source citations as pill badges. Values are user-controlled (uploaded file
    names), so every citation is HTML-escaped before interpolation."""
    if not citations:
        return
    pills = "".join(f'<span class="acme-citation-pill">{html.escape(citation)}</span>' for citation in citations)
    st.markdown(f'<div class="acme-citation-row">{pills}</div>', unsafe_allow_html=True)


def render_confidence(confidence: float | None, confidence_label: str | None) -> None:
    """Show how strong the best supporting evidence was - not the model's fluency,
    and not lowered by a faithfulness-gate fallback (see _compute_confidence in
    src/service.py). Omitted entirely for no-answer responses, where it's meaningless."""
    if confidence is None or confidence_label is None:
        return
    icon = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(confidence_label, "")
    css_class = f"acme-confidence-badge--{confidence_label.lower()}"
    st.markdown(
        f'<span class="acme-confidence-badge {css_class}">{icon} {confidence_label} confidence ({confidence:.0%})</span>',
        unsafe_allow_html=True,
    )


def render_fallback_notice(used_fallback: bool) -> None:
    """Surface it when a generated answer failed the faithfulness check (or the
    generation call itself failed) and the extractive fallback is shown instead -
    previously this only showed up in the log, invisible to the person asking."""
    if used_fallback:
        st.caption("ℹ️ The generated answer didn't pass the groundedness check, so this shows the retrieved evidence directly instead.")


def initialize_state() -> None:
    RagService.cleanup_expired_workspaces()
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("indexed_uploads", set())
    st.session_state.setdefault("workspace_id", uuid.uuid4().hex)
    # Not setdefault(...): Python evaluates RagService(...) eagerly on every call
    # regardless of whether the key already exists, so setdefault would silently
    # construct (and discard) a throwaway RagService - LanceDB connection, provider
    # selection, and all - on every single rerun (i.e. every click or keystroke).
    # Confirmed by the new event=session_start log firing repeatedly per session.
    if "service" not in st.session_state:
        st.session_state.service = RagService(workspace_id=st.session_state.workspace_id)


def main() -> None:
    inject_theme()
    initialize_state()
    service: RagService = st.session_state.service

    render_header()

    with st.sidebar:
        st.header("📚 Knowledge base")
        with st.expander("⚙️ System status"):
            for name, value in service.health_check().items():
                st.caption(f"{name.replace('_', ' ').title()}: {value}")
        uploaded_files = st.file_uploader(
            "Upload documents",
            type=["xlsx", "xls", "csv", "pptx", "ppt", "docx", "doc"],
            accept_multiple_files=True,
            help="Legacy .xls, .ppt, and .doc files are identified and receive a conversion message in this prototype.",
        )
        if st.button("Index uploaded files", type="primary", disabled=not uploaded_files):
            for uploaded in uploaded_files or []:
                payload = uploaded.getvalue()
                fingerprint = f"{uploaded.name}:{hashlib.sha256(payload).hexdigest()}"
                if fingerprint in st.session_state.indexed_uploads:
                    st.info(f"{uploaded.name} is already indexed in this session.")
                    continue
                try:
                    with st.spinner(f"Indexing {uploaded.name}..."):
                        result = service.index_document(uploaded.name, payload)
                    st.session_state.indexed_uploads.add(fingerprint)
                    if result.status == "unchanged":
                        st.info(f"{uploaded.name} is unchanged; existing index reused.")
                    else:
                        st.success(f"{result.status.title()} {uploaded.name}: {result.record_count} records, {result.chunk_count} chunks.")
                    for warning in result.warnings:
                        st.warning(warning)
                except DocumentParseError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error(f"Unable to index {uploaded.name}. Check the file and try again.")
        st.divider()
        st.metric("Indexed documents", service.store.document_count())
        for document in service.store.documents():
            st.caption(document)
        st.subheader("🔎 Retrieval filters")
        file_options = ["All files", *service.store.filter_values("file_name")]
        type_options = ["All types", *service.store.filter_values("file_type")]
        sheet_options = ["All sheets", *service.store.filter_values("sheet_name")]
        slide_options = ["All slides", *service.store.filter_values("slide_number")]
        section_options = ["All sections", *service.store.filter_values("section_title")]
        selected_file = st.selectbox("File", file_options)
        selected_type = st.selectbox("Format", type_options)
        selected_sheet = st.selectbox("Excel sheet", sheet_options)
        selected_slide = st.selectbox("PowerPoint slide", slide_options)
        selected_section = st.selectbox("Word section", section_options)
        confirm_clear = st.checkbox("I understand this removes this session's index")
        if st.button("Clear knowledge base", disabled=not confirm_clear):
            service.store.clear()
            st.session_state.indexed_uploads.clear()
            st.session_state.messages.clear()
            st.rerun()
        with st.expander("Demo data"):
            st.write("Try the files in `sample_data/`, then ask: “What was South region's Q1 revenue and target attainment?”")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                render_confidence(message.get("confidence"), message.get("confidence_label"))
                render_citations(message.get("citations", []))
                render_fallback_notice(message.get("used_fallback", False))

    prompt = st.chat_input("Ask a question about the indexed documents")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            spinner_text = (
                "Searching indexed documents and generating an answer locally (can take up to a minute on CPU)..."
                if isinstance(service.generator, LocalLLMGenerator)
                else "Searching indexed documents..."
            )
            with st.spinner(spinner_text):
                filters = {}
                if selected_file != "All files":
                    filters["file_name"] = selected_file
                if selected_type != "All types":
                    filters["file_type"] = selected_type
                if selected_sheet != "All sheets":
                    filters["sheet_name"] = selected_sheet
                if selected_slide != "All slides":
                    filters["slide_number"] = int(selected_slide)
                if selected_section != "All sections":
                    filters["section_title"] = selected_section
                response = service.answer(prompt, filters)
            st.markdown(response.answer)
            render_confidence(response.confidence, response.confidence_label)
            citations = [source.citation() for source in response.sources]
            render_citations(citations)
            render_fallback_notice(response.used_extractive_fallback)
            with st.expander("Retrieved evidence"):
                if response.evidence:
                    for result in response.evidence:
                        st.markdown(f"**{result.chunk.source.citation()}** — relevance {result.score:.2f}")
                        st.code(result.chunk.text, language=None)
                else:
                    st.write("No relevant evidence was retrieved.")
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response.answer,
                "citations": citations,
                "used_fallback": response.used_extractive_fallback,
                "confidence": response.confidence,
                "confidence_label": response.confidence_label,
            }
        )


if __name__ == "__main__":
    main()
