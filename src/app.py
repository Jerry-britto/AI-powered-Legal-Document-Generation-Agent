"""
Streamlit Web Interface for AI-Powered Legal Document Generation Agent.
Features sequential step execution tracing, direct .docx Word document download,
and in-browser Evaluation Report display with dark-mode white headings.
"""

import os
import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv

from src.graph.agent_worfklow import build_legal_doc_agent_graph
from src.utils.parser_utils import ingest_case_document
from src.schemas.entity_schema import EvaluationReportSchema

load_dotenv()

# Page configuration
st.set_page_config(
    page_title="AI-Powered Legal Document Generation Agent",
    page_icon="⚖️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS ensuring high-contrast white headings and clean layout
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    .reportview-container .main .block-container {
        max-width: 900px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    
    /* Force white color on all headers and prominent text */
    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: #ffffff !important;
        font-weight: 700;
    }
    
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #ffffff !important;
        margin-bottom: 0.3rem;
    }
    
    .sub-title {
        font-size: 1.05rem;
        color: #cbd5e1 !important;
        margin-bottom: 1.8rem;
    }
    
    /* Trace card styling */
    .trace-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
        color: #f1f5f9;
    }
    
    .trace-title {
        font-weight: 600;
        font-size: 1.05rem;
        color: #60a5fa !important;
        margin-bottom: 6px;
    }
    
    /* Download box */
    .download-card {
        background-color: #0f172a;
        border: 1px solid #3b82f6;
        border-radius: 10px;
        padding: 24px;
        text-align: center;
        margin-top: 1rem;
        margin-bottom: 2rem;
    }
    
    .doc-meta {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-top: 8px;
    }
    
    /* Score banner */
    .score-card {
        background: linear-gradient(135deg, #1e3a8a 0%, #1e293b 100%);
        border-radius: 10px;
        padding: 20px;
        border: 1px solid #3b82f6;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# Main Section: Title, Subtitle, and Two Inputs
# -------------------------------------------------------------
st.markdown('<div class="main-title">⚖️ AI-Powered Legal Document Generation Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">High Court of Judicature at Bombay • Writ Jurisdiction • Affidavit in Reply</div>', unsafe_allow_html=True)

# Control 1: Upload the PDF
uploaded_file = st.file_uploader(
    "Upload Case Information (PDF)",
    type=["pdf", "txt", "md"],
    help="Upload the case details, parties, and substantive reply points (PDF, TXT, or MD)."
)

# Control 2: Execute or Run Agent Button
run_agent = st.button("🚀 Execute / Run Agent", type="primary", use_container_width=True)

# Session state initialization
if "execution_completed" not in st.session_state:
    st.session_state.execution_completed = False
if "final_state" not in st.session_state:
    st.session_state.final_state = None

# -------------------------------------------------------------
# Agent Execution & Step Traces
# -------------------------------------------------------------
if run_agent:
    st.session_state.execution_completed = False
    st.session_state.final_state = None

    st.markdown("### 📋 Agent Execution Traces")
    trace_placeholder = st.container()

    with st.status("Executing Agent Stages...", expanded=True) as status:
        try:
            # Step 1: Ingestion
            st.write("📥 **Ingesting Input Document**...")
            if uploaded_file is None:
                raise ValueError("Upload a case information document before running the agent.")
            raw_text, source_meta = ingest_case_document(
                uploaded_file.getvalue(),
                uploaded_file.name,
            )
            st.write(
                f"✓ Document parsed ({source_meta['character_count']} characters loaded; "
                f"{'cache hit' if source_meta['cache_hit'] else 'cached new parse'})."
            )

            # Initialize LangGraph
            st.write("⚙️ **Initializing LangGraph State Workflow**...")
            graph = build_legal_doc_agent_graph()
            initial_state = {
                "raw_document_text": raw_text,
                **source_meta,
                "llm_provider": "gemini",
                "simulated_error": "none",
                "current_step": "Starting",
                "status": "initialized",
                "step_traces": []
            }

            st.write("🧠 **Running Extraction, Drafting & Dual Evaluation Nodes**...")
            final_state = graph.invoke(initial_state)

            st.session_state.final_state = final_state
            st.session_state.execution_completed = True
            status.update(label="✅ All Stages Completed Successfully!", state="complete", expanded=False)

        except Exception as e:
            status.update(label="❌ Execution Failed", state="error")
            st.error(f"Error during agent execution: {str(e)}")

# -------------------------------------------------------------
# Display Step Traces
# -------------------------------------------------------------
if st.session_state.execution_completed and st.session_state.final_state:
    state = st.session_state.final_state
    traces = state.get("step_traces", [])

    st.markdown("### 🔍 Execution Step Traces")
    with st.expander("View Detailed Step Trace Logs", expanded=True):
        for trace in traces:
            s_num = trace.get("step_number", "")
            s_name = trace.get("step_name", "")
            s_status = trace.get("status", "")
            details = trace.get("details", [])

            st.markdown(f"""
            <div class="trace-card">
                <div class="trace-title">Step {s_num}: {s_name} &nbsp;•&nbsp; <span style="color: #4ade80;">{s_status}</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            for item in details:
                st.markdown(f"- {item}")
            st.write("")

    # -------------------------------------------------------------
    # Final Outputs: Download Affidavit (.docx) & View Evaluation Report
    # -------------------------------------------------------------
    st.markdown("---")
    st.markdown("### 📥 Final Legal Document: Affidavit in Reply")
    st.caption("The generated court filing is typeset strictly according to High Court formatting standards (1.25\" margin, Times New Roman 12pt, 10 mandatory sections).")

    docx_path = state.get("docx_path")
    if Path(docx_path).exists():
        with open(docx_path, "rb") as f:
            docx_data = f.read()

        intermediate = state.get("intermediate_data")
        intermediate_data = intermediate.model_dump() if hasattr(intermediate, "model_dump") else (intermediate or {})
        case_details = intermediate_data.get("case_details", {})
        deponent = intermediate_data.get("deponent", {})
        st.markdown(f"""
        <div class="download-card">
            <h3 style="color: #ffffff !important; margin-bottom: 8px;">Affidavit in Reply (.docx)</h3>
            <p class="doc-meta">Forum: {case_details.get("court", "N/A")} • Proceeding: {case_details.get("proceeding_type", "N/A")} No. {case_details.get("case_number", "N/A")} of {case_details.get("year", "N/A")}<br>
            Deponent: {deponent.get("name", "N/A")}, {deponent.get("designation", "N/A")} on behalf of {case_details.get("filed_on_behalf_of", "N/A")}</p>
        </div>
        """, unsafe_allow_html=True)

        st.download_button(
            label="📥 Download Affidavit in Reply (.docx)",
            data=docx_data,
            file_name="Affidavit_in_Reply.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("### 📊 Evaluation Report")
    report = state.get("evaluation_report")
    if report:
        if isinstance(report, dict):
            report = EvaluationReportSchema(**report)

        # Overall Quality Score Banner
        st.markdown(f"""
        <div class="score-card">
            <h2 style="color: #60a5fa !important; margin: 0;">Overall Quality Score: {report.overall_score}/100</h2>
            <p style="color: #e2e8f0; margin-top: 6px; margin-bottom: 0; font-size: 0.95rem;">
                {report.score_calculation_explanation}
            </p>
        </div>
        """, unsafe_allow_html=True)

        # Dimension Breakdown
        st.markdown("#### Dimension Breakdown")
        dim_cols = st.columns(6)
        for idx, (dim_name, ds) in enumerate(report.dimension_scores.items()):
            with dim_cols[idx % 6]:
                st.metric(label=dim_name, value=f"{ds.score:.0f}/100")

        st.markdown("")
        # Programmatic Deterministic Checks Table
        st.markdown("#### Deterministic Programmatic Checks (Zero-Tolerance Engine)")
        checks_rows = []
        for c in report.deterministic_checks:
            checks_rows.append({
                "Rule Check": c.name,
                "Status": "✅ PASS" if c.passed else "❌ FAIL",
                "Expected": c.expected,
                "Actual Output": c.actual
            })
        st.dataframe(checks_rows, use_container_width=True, hide_index=True)

        # Detected Issues or Clean Audit
        if report.detected_issues:
            st.markdown("#### Audit Findings & Issues")
            for i, issue in enumerate(report.detected_issues, 1):
                st.warning(f"**{i}. [{issue.get('severity', 'ISSUE')}] {issue.get('dimension')}**: {issue.get('message')}")
        else:
            st.success("✅ Zero structural, factual, or formatting defects detected. All 6 High Court compliance checks passed.")

        # Download Report JSON Button
        json_path = state.get("json_path")
        if Path(json_path).exists():
            with open(json_path, "r", encoding="utf-8") as f:
                st.download_button(
                    label="📥 Download Evaluation Report (.json)",
                    data=f.read(),
                    file_name="Evaluation_Report.json",
                    mime="application/json",
                    use_container_width=True
                )
