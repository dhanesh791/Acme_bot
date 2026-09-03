from __future__ import annotations

import hashlib
import uuid

import streamlit as st

from src.parsers import DocumentParseError
from src.service import RagService


st.set_page_config(page_title="Acme Retail Knowledge Chat", page_icon="🛍️", layout="wide")


def initialize_state() -> None:
    RagService.cleanup_expired_workspaces()
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("indexed_uploads", set())
    st.session_state.setdefault("workspace_id", uuid.uuid4().hex)
    st.session_state.setdefault("service", RagService(workspace_id=st.session_state.workspace_id))


def show_sources(response) -> None:
    if response.sources:
        st.markdown("**Sources**")
        for source in response.sources:
            st.caption(source.citation())


def main() -> None:
    initialize_state()
    service: RagService = st.session_state.service

    st.title("Acme Retail Knowledge Chat")
    st.caption("Ask questions across uploaded Excel, CSV, and PowerPoint documents. Answers are limited to indexed evidence.")

    with st.sidebar:
        st.header("Knowledge base")
        with st.expander("System status"):
            for name, value in service.health_check().items():
                st.caption(f"{name.replace('_', ' ').title()}: {value}")
        uploaded_files = st.file_uploader(
            "Upload documents",
            type=["xlsx", "xls", "csv", "pptx", "ppt"],
            accept_multiple_files=True,
            help="Legacy .xls and .ppt files are identified and receive a conversion message in this prototype.",
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
        st.subheader("Retrieval filters")
        file_options = ["All files", *service.store.filter_values("file_name")]
        type_options = ["All types", *service.store.filter_values("file_type")]
        sheet_options = ["All sheets", *service.store.filter_values("sheet_name")]
        slide_options = ["All slides", *service.store.filter_values("slide_number")]
        selected_file = st.selectbox("File", file_options)
        selected_type = st.selectbox("Format", type_options)
        selected_sheet = st.selectbox("Excel sheet", sheet_options)
        selected_slide = st.selectbox("PowerPoint slide", slide_options)
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
                for citation in message.get("citations", []):
                    st.caption(citation)

    prompt = st.chat_input("Ask a question about the indexed documents")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Searching indexed documents..."):
                filters = {}
                if selected_file != "All files":
                    filters["file_name"] = selected_file
                if selected_type != "All types":
                    filters["file_type"] = selected_type
                if selected_sheet != "All sheets":
                    filters["sheet_name"] = selected_sheet
                if selected_slide != "All slides":
                    filters["slide_number"] = int(selected_slide)
                response = service.answer(prompt, filters)
            st.markdown(response.answer)
            citations = [source.citation() for source in response.sources]
            for citation in citations:
                st.caption(citation)
            with st.expander("Retrieved evidence"):
                if response.evidence:
                    for result in response.evidence:
                        st.markdown(f"**{result.chunk.source.citation()}** — relevance {result.score:.2f}")
                        st.code(result.chunk.text, language=None)
                else:
                    st.write("No relevant evidence was retrieved.")
        st.session_state.messages.append(
            {"role": "assistant", "content": response.answer, "citations": citations}
        )


if __name__ == "__main__":
    main()
