"""Streamlit interface for the legal document generation agent."""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from dotenv import load_dotenv

from src.graph.agent_worfklow import build_legal_doc_agent_graph
from src.utils.parser_utils import ingest_case_document
from src.schemas.schema_info import EvaluationReportSchema

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
                st.write(f"{s_num}. {s_name}")


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
                width="stretch",
                key="download_affidavit",
            )
    else:
        st.warning("The generated affidavit file is not available.")

    st.markdown("---")
    st.markdown("### Evaluation Summary")
    report = state.get("evaluation_report")
    if not report:
        st.info("Evaluation information is not available.")
        return

    if isinstance(report, dict):
        report = EvaluationReportSchema(**report)

    passed_checks = sum(check.passed for check in report.deterministic_checks)
    total_checks = len(report.deterministic_checks)
    issue_count = len(report.detected_issues)
    readiness_is_ready = getattr(report, "filing_ready", False)
    readiness_status = getattr(
        report,
        "readiness_status",
        "READY" if readiness_is_ready else "NOT_READY",
    )

    if readiness_is_ready:
        st.success(
            f"✓ READY FOR FILING REVIEW · {passed_checks}/{total_checks} deterministic checks passed",
            icon="✅",
        )
    else:
        st.error(
            f"⚠ NOT READY FOR FILING REVIEW · {issue_count} finding(s) require attention",
            icon="⚠️",
        )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Overall score", f"{report.overall_score:.1f}/100")
    summary_cols[1].metric("Checks passed", f"{passed_checks}/{total_checks}")
    summary_cols[2].metric("Findings", issue_count)
    summary_cols[3].metric("Readiness", readiness_status)

    st.caption(report.score_calculation_explanation)

    st.markdown("#### Dimension Scorecard")
    dimensions = list(report.dimension_scores.items())
    for row_start in range(0, len(dimensions), 3):
        dimension_cols = st.columns(3)
        for col, (dim_name, dimension) in zip(dimension_cols, dimensions[row_start:row_start + 3]):
            status = "PASS" if dimension.score >= 90 else "WARN" if dimension.score >= 70 else "FAIL"
            status_color = {"PASS": "#198754", "WARN": "#b26a00", "FAIL": "#b02a37"}[status]
            finding_count = len(dimension.issues_detected)
            with col:
                st.markdown(
                    f"""
                    <div style="border:1px solid #d9dee3;border-radius:10px;padding:14px;
                                margin-bottom:12px;min-height:145px;">
                      <div style="font-weight:600;font-size:0.95rem;">{dim_name}</div>
                      <div style="font-size:1.65rem;font-weight:700;margin:5px 0;">
                        {dimension.score:.1f}<span style="font-size:0.9rem;">/100</span>
                      </div>
                      <div style="height:8px;background:#e9ecef;border-radius:5px;">
                        <div style="width:{dimension.score}%;height:8px;background:{status_color};
                                    border-radius:5px;"></div>
                      </div>
                      <div style="color:{status_color};font-weight:600;font-size:0.8rem;
                                  margin-top:8px;">{status} · {dimension.weight:.0%} weight ·
                        {finding_count} finding(s)</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.caption(dimension.explanation)

    st.markdown("#### Deterministic Compliance")
    st.caption("Objective checks against the extracted case and affidavit rules.")
    checks_rows = [
        {
            "Rule Check": c.name,
            "Status": "✅ PASS" if c.passed else "❌ FAIL",
            "Expected": c.expected,
            "Actual Output": c.actual,
        }
        for c in report.deterministic_checks
    ]
    st.dataframe(checks_rows, width="stretch", hide_index=True)

    if report.detected_issues:
        st.markdown("#### Findings and Recommended Actions")
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_issues = sorted(
            report.detected_issues,
            key=lambda issue: severity_order.get(issue.get("severity", "LOW"), 4),
        )
        severity_icons = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}
        for index, issue in enumerate(sorted_issues, 1):
            severity = issue.get("severity", "ISSUE")
            icon = severity_icons.get(severity, "⚠️")
            with st.expander(
                f"{icon} {severity} · {issue.get('dimension', 'Evaluation')} · Finding {index}",
                expanded=severity in {"CRITICAL", "HIGH"},
            ):
                st.write(issue.get("message", "No description provided."))
                st.caption(f"Rule: {issue.get('rule', 'Not specified')}")

        readiness_reasons = getattr(report, "readiness_reasons", [])
        if readiness_reasons:
            st.markdown("##### Recommended actions")
            for reason in readiness_reasons:
                st.markdown(f"- Resolve: {reason}")
    else:
        st.success(
            "No deterministic or audit findings were reported for this document."
        )

    st.markdown("#### Downloadable Reports")
    json_path = state.get("json_path", "outputs/Evaluation_Report.json")
    evaluation_md_path = state.get(
        "evaluation_md_path",
        "outputs/Evaluation_Report.md",
    )
    download_cols = st.columns(2)
    if Path(json_path).exists():
        with open(json_path, "r", encoding="utf-8") as f:
            with download_cols[0]:
                st.download_button(
                    label="Download evaluation report (.json)",
                    data=f.read(),
                    file_name="Evaluation_Report.json",
                    mime="application/json",
                    width="stretch",
                    key="download_evaluation_report",
                )
    if Path(evaluation_md_path).exists():
        with open(evaluation_md_path, "r", encoding="utf-8") as f:
            with download_cols[1]:
                st.download_button(
                    label="Download evaluation report (.md)",
                    data=f.read(),
                    file_name="Evaluation_Report.md",
                    mime="text/markdown",
                    width="stretch",
                    key="download_evaluation_markdown",
                )


def render_outputs(output_placeholder, state):
    with output_placeholder.container():
        render_outputs_content(state)


# Page configuration
st.set_page_config(
    page_title="AI-Powered Legal Document Generation Agent",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# -------------------------------------------------------------
# Main Section: Title, Subtitle, and Two Inputs
# -------------------------------------------------------------
st.title("AI-Powered Legal Document Generation Agent")

# Control 1: Upload the PDF
uploaded_file = st.file_uploader(
    "Upload one Case Information file",
    type=["pdf", "txt", "md"],
    accept_multiple_files=False,
    help="Upload one file containing the case details, parties, and substantive reply points (PDF, TXT, or MD).",
)

# Session state initialization
if "execution_completed" not in st.session_state:
    st.session_state.execution_completed = False
if "final_state" not in st.session_state:
    st.session_state.final_state = None
if "execution_state" not in st.session_state:
    st.session_state.execution_state = None
if "execution_requested" not in st.session_state:
    st.session_state.execution_requested = False
if "execution_in_progress" not in st.session_state:
    st.session_state.execution_in_progress = False
if "execution_error" not in st.session_state:
    st.session_state.execution_error = None

# -------------------------------------------------------------
# Agent Execution & Single Step Trace
# -------------------------------------------------------------
run_agent = st.button(
    "🚀 Execute / Run Agent",
    type="primary",
    width="stretch",
    disabled=st.session_state.execution_in_progress,
)

if run_agent and not st.session_state.execution_in_progress:
    st.session_state.execution_requested = True
    st.session_state.execution_in_progress = True
    st.session_state.execution_completed = False
    st.session_state.final_state = None
    st.session_state.execution_state = None
    st.session_state.execution_error = None
    st.rerun()

trace_state = st.session_state.final_state or st.session_state.execution_state
trace_placeholder = None
output_placeholder = None
if st.session_state.execution_requested or trace_state:
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

if st.session_state.execution_error:
    st.error(f"Error during agent execution: {st.session_state.execution_error}")
    st.session_state.execution_error = None

if st.session_state.execution_requested:
    if uploaded_file is None:
        st.session_state.execution_error = "Upload a case information document before running the agent."
    else:
        try:
            # Keep ingestion and workflow stages in the same trace stream for
            # both new parses and cache hits.
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
                    {"step_number": 1, "step_name": "Input ingestion", "status": "completed"},
                    {"step_number": 2, "step_name": "Workflow initialization", "status": "completed"},
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

        except Exception as exc:
            st.session_state.execution_error = str(exc)

    st.session_state.execution_requested = False
    st.session_state.execution_in_progress = False
    st.rerun()

if st.session_state.execution_completed and st.session_state.final_state:
    state = st.session_state.final_state

    # The live trace placeholder already contains the final trace; on later
    # reruns, render the persisted trace into the same single surface.
    if trace_placeholder is not None:
        render_trace_log(trace_placeholder, state.get("step_traces", []))
    if output_placeholder is not None and run_agent:
        render_outputs(output_placeholder, state)
