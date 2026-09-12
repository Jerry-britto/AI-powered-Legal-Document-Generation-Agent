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


def render_trace_log(trace_placeholder, traces):
    """Render the single trace log used during and after execution."""
    with trace_placeholder.container():
        with st.expander("Execution step trace logs", expanded=True):
            if not traces:
                st.info("Waiting for the first execution step...")
                return

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


def render_outputs_content(state):
    """Render completed document and evaluation outputs in the Output tab."""
    docx_path = state.get("docx_path", "outputs/Affidavit_in_Reply.docx")
    if Path(docx_path).exists():
        with open(docx_path, "rb") as f:
            st.download_button(
                label="Download Affidavit in Reply (.docx)",
                data=f.read(),
                file_name="Affidavit_in_Reply.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True,
                key="download_affidavit",
            )
    else:
        st.warning("The generated affidavit file is not available.")

    st.markdown("---")
    st.markdown("### 📊 Evaluation Report")
    report = state.get("evaluation_report")
    if not report:
        st.info("Evaluation information is not available.")
        return

    if isinstance(report, dict):
        report = EvaluationReportSchema(**report)

    st.markdown(f"""
    <div class="score-card">
        <h2 style="color: #60a5fa !important; margin: 0;">Overall Quality Score: {report.overall_score}/100</h2>
        <p style="color: #e2e8f0; margin-top: 6px; margin-bottom: 0; font-size: 0.95rem;">
            {report.score_calculation_explanation}
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### Dimension Breakdown")
    dim_cols = st.columns(6)
    for idx, (dim_name, ds) in enumerate(report.dimension_scores.items()):
        with dim_cols[idx % 6]:
            st.metric(label=dim_name, value=f"{ds.score:.0f}/100")

    st.markdown("")
    st.markdown("#### Deterministic Programmatic Checks (Zero-Tolerance Engine)")
    checks_rows = [
        {
            "Rule Check": c.name,
            "Status": "✅ PASS" if c.passed else "❌ FAIL",
            "Expected": c.expected,
            "Actual Output": c.actual,
        }
        for c in report.deterministic_checks
    ]
    st.dataframe(checks_rows, use_container_width=True, hide_index=True)

    if report.detected_issues:
        st.markdown("#### Audit Findings & Issues")
        for i, issue in enumerate(report.detected_issues, 1):
            st.warning(
                f"**{i}. [{issue.get('severity', 'ISSUE')}] "
                f"{issue.get('dimension')}**: {issue.get('message')}"
            )
    else:
        st.success(
            "✅ Zero structural, factual, or formatting defects detected. "
            "All 6 High Court compliance checks passed."
        )

    json_path = state.get("json_path", "outputs/Evaluation_Report.json")
    if Path(json_path).exists():
        with open(json_path, "r", encoding="utf-8") as f:
            st.download_button(
                label="📥 Download Evaluation Report (.json)",
                data=f.read(),
                file_name="Evaluation_Report.json",
                mime="application/json",
                use_container_width=True,
                key="download_evaluation_report",
            )


def render_outputs(output_placeholder, state):
    with output_placeholder.container():
        render_outputs_content(state)


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
if "execution_state" not in st.session_state:
    st.session_state.execution_state = None

# -------------------------------------------------------------
# Agent Execution & Single Step Trace
# -------------------------------------------------------------
if run_agent:
    st.session_state.execution_completed = False
    st.session_state.final_state = None
    st.session_state.execution_state = None

trace_state = st.session_state.final_state or st.session_state.execution_state
trace_placeholder = None
output_placeholder = None
if run_agent or trace_state:
    trace_tab, output_tab = st.tabs(["Trace", "Output"])
    with trace_tab:
        st.markdown("### 📋 Agent Execution Traces")
        trace_placeholder = st.empty()
    with output_tab:
        output_placeholder = st.empty()
        if st.session_state.execution_completed and st.session_state.final_state:
            render_outputs(output_placeholder, st.session_state.final_state)
        else:
            output_placeholder.info("Output will be available after the agent completes successfully.")

if run_agent:
    if uploaded_file is None:
        st.error("Upload a case information document before running the agent.")
        st.stop()

    try:
        # The ingestion and workflow setup entries are part of the same trace
        # list that LangGraph extends as each node completes.
        raw_text, source_meta = ingest_case_document(
            uploaded_file.getvalue(),
            uploaded_file.name,
        )
        initial_state = {
            "raw_document_text": raw_text,
            **source_meta,
            "llm_provider": "gemini",
            "simulated_error": "none",
            "current_step": "Starting",
            "status": "initialized",
            "step_traces": [
                {
                    "step_number": 1,
                    "step_name": "Input ingestion",
                    "status": "completed",
                    "details": [
                        f"Document parsed ({source_meta['character_count']} characters loaded; "
                        f"{'cache hit' if source_meta['cache_hit'] else 'cached new parse'})."
                    ],
                },
                {
                    "step_number": 2,
                    "step_name": "Workflow initialization",
                    "status": "completed",
                    "details": ["Initialized the LangGraph state workflow."],
                },
            ],
        }
        st.session_state.execution_state = initial_state
        render_trace_log(trace_placeholder, initial_state["step_traces"])

        graph = build_legal_doc_agent_graph()
        for streamed_state in graph.stream(initial_state, stream_mode="values"):
            st.session_state.execution_state = streamed_state
            render_trace_log(trace_placeholder, streamed_state.get("step_traces", []))

        st.session_state.final_state = st.session_state.execution_state
        st.session_state.execution_completed = True

    except Exception as e:
        st.error(f"Error during agent execution: {str(e)}")

if st.session_state.execution_completed and st.session_state.final_state:
    state = st.session_state.final_state

    # The live trace placeholder already contains the final trace; on later
    # reruns, render the persisted trace into the same single surface.
    if trace_placeholder is not None:
        render_trace_log(trace_placeholder, state.get("step_traces", []))
    if output_placeholder is not None and run_agent:
        render_outputs(output_placeholder, state)
