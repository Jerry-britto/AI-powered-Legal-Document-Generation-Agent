"""LangGraph orchestration for extraction, drafting, evaluation, and persistence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.evals.scoring import evaluate_affidavit_document
from src.schemas.schema_info import CaseInformationSchema
from src.graph.state import AgentWorkflowState
from src.utils.docx_generator import create_affidavit_docx
from src.utils.llm import get_llm

ARTIFACTS_DIR = Path("artifacts")
OUTPUTS_DIR = Path("outputs")


def _trace(state: AgentWorkflowState, name: str, details: list[str]) -> list[Dict[str, Any]]:
    traces = list(state.get("step_traces", []))
    traces.append({"step_number": len(traces) + 1, "step_name": name, "status": "completed", "details": details})
    return traces


def extract_entities(state: AgentWorkflowState) -> Dict[str, Any]:
    llm = get_llm(state.get("llm_provider", "gemini"), state.get("llm_model"))
    structured_llm = llm.with_structured_output(CaseInformationSchema)
    prompt = f"""Extract the supplied case information into the exact structured schema.
Do not invent facts. Preserve names, numbers, dates, addresses, exhibits, prayer
items, and reply points exactly as supplied. Include source_evidence when clear.

CASE INFORMATION:
{state["raw_document_text"]}
"""
    case_info = structured_llm.invoke(prompt)
    if not isinstance(case_info, CaseInformationSchema):
        case_info = CaseInformationSchema.model_validate(case_info)
    return {
        "intermediate_data": case_info,
        "current_step": "Entity extraction",
        "step_traces": _trace(state, "Entity extraction", [
            f"Extracted {len(case_info.reply_points)} reply points.",
            f"Identified {len(case_info.case_details.respondents)} respondents.",
        ]),
    }


def validate_entities(state: AgentWorkflowState) -> Dict[str, Any]:
    case_info = CaseInformationSchema.model_validate(state["intermediate_data"])
    if not case_info.reply_points:
        raise ValueError("The case information must contain at least one reply point.")
    return {
        "intermediate_data": case_info,
        "pre_generation_errors": [],
        "current_step": "Pre-generation validation",
        "step_traces": _trace(state, "Pre-generation validation", [
            "Pydantic and respondent/deponent business rules passed.",
        ]),
    }


def map_content(state: AgentWorkflowState) -> Dict[str, Any]:
    case_info = state["intermediate_data"]
    body_paragraphs = []
    for point in case_info.reply_points:
        text = point.title
        if point.content_bullets:
            text += ". " + " ".join(point.content_bullets)
        if point.exhibit_reference:
            text += f" {point.exhibit_reference}."
        body_paragraphs.append({"number": point.point_number, "text": text})
    mapped = {
        "case_details": case_info.case_details.model_dump(mode="json"),
        "deponent": case_info.deponent.model_dump(mode="json"),
        "body_paragraphs": body_paragraphs,
        "prayers": case_info.prayer.items,
        "attestation": case_info.attestation.model_dump(mode="json"),
        "advocate": case_info.advocate.model_dump(mode="json"),
    }
    return {
        "mapped_sections": mapped,
        "current_step": "Content mapping",
        "step_traces": _trace(state, "Content mapping", [
            f"Mapped {len(body_paragraphs)} numbered reply paragraphs.",
            f"Mapped {len(case_info.prayer.items)} lettered prayer items.",
        ]),
    }


def _render_affidavit(mapped: Dict[str, Any]) -> str:
    case = mapped["case_details"]
    dep = mapped["deponent"]
    paragraphs = mapped["body_paragraphs"]
    lines = [
        case["court"].upper(),
        case["jurisdiction"].upper(),
        f'{case["proceeding_type"].upper()} NO. {case["case_number"]} OF {case["year"]}',
        "",
        f'{case["petitioner"]} ...Petitioner',
        "VERSUS",
    ]
    lines.extend(f"{idx}. {name} ...Respondent No.{idx}" for idx, name in enumerate(case["respondents"], 1))
    lines.extend([
        "",
        f'AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO. {case["answering_respondent_number"]}',
        "",
        (
            f'I, {dep["name"]}, having office at {dep["address"]}, the {dep["designation"]} '
            f'of Respondent No.{case["answering_respondent_number"]} above named, do hereby '
            f'{dep["verification_verb"]} and state as under:'
        ),
        "",
    ])
    lines.extend(f'{item["number"]}. {item["text"]}' for item in paragraphs)
    lines.extend(["", "PRAYER", "I therefore respectfully pray that this Hon'ble Court may be pleased to:"])
    lines.extend(f"({chr(97 + index)}) {item}" for index, item in enumerate(mapped["prayers"]))
    attestation = mapped["attestation"]
    lines.extend([
        "",
        f'Solemnly affirmed at {attestation["place"]} on this {attestation["date_ordinal"]}    DEPONENT',
        "",
        "VERIFICATION",
        (
            f'I, {dep["name"]}, the Deponent above named, do hereby verify that the contents '
            f'of paragraphs 1 to {len(paragraphs)} and the Prayer above are true and correct '
            "to my knowledge and belief and that nothing material has been concealed therefrom."
        ),
        f'Verified at {attestation["place"]} on this {attestation["date_ordinal"]}.    DEPONENT',
        "",
        mapped["advocate"]["firm_name"].upper(),
        f'Advocates for the {mapped["advocate"]["acting_for"]}.',
    ])
    return "\n".join(lines)


def generate_document(state: AgentWorkflowState) -> Dict[str, Any]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    mapped = state["mapped_sections"]
    generated_text = _render_affidavit(mapped)
    md_path = OUTPUTS_DIR / "Affidavit_in_Reply.md"
    docx_path = OUTPUTS_DIR / "Affidavit_in_Reply.docx"
    md_path.write_text(generated_text + "\n", encoding="utf-8")
    create_affidavit_docx(mapped, str(docx_path))
    return {
        "generated_text": generated_text,
        "md_path": str(md_path),
        "docx_path": str(docx_path),
        "current_step": "Document generation",
        "step_traces": _trace(state, "Document generation", [f"Wrote {md_path}.", f"Wrote {docx_path}."]),
    }


def evaluate_document(state: AgentWorkflowState) -> Dict[str, Any]:
    llm = get_llm(state.get("llm_provider", "gemini"), state.get("llm_model"))
    report = evaluate_affidavit_document(
        generated_text=state["generated_text"],
        case_info=state["intermediate_data"],
        llm=llm,
        simulated_error=state.get("simulated_error", "none"),
    )
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUTS_DIR / "Evaluation_Report.json"
    evaluation_md_path = OUTPUTS_DIR / "Evaluation_Report.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    issues = "\n".join(f"- {issue['message']}" for issue in report.detected_issues) or "- None detected."
    dimensions = "\n".join(f"- **{name}:** {score.score}/100" for name, score in report.dimension_scores.items())
    evaluation_md_path.write_text(
        f"# Evaluation Report\n\n**Overall Score:** {report.overall_score}/100\n\n"
        f"{report.score_calculation_explanation}\n\n## Dimension Scores\n\n{dimensions}\n\n"
        f"## Issues\n\n{issues}\n",
        encoding="utf-8",
    )
    return {
        "evaluation_report": report,
        "json_path": str(json_path),
        "evaluation_md_path": str(evaluation_md_path),
        "current_step": "Evaluation",
        "step_traces": _trace(state, "Evaluation", [
            f"Overall score: {report.overall_score}/100.",
            f"Deterministic checks passed: {report.passed_all_deterministic}.",
        ]),
    }


def finalize_run(state: AgentWorkflowState) -> Dict[str, Any]:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    parsed_input_path = ARTIFACTS_DIR / "Parsed_Case_Information.md"
    parsed_input_path.write_text(state["raw_document_text"] + "\n", encoding="utf-8")
    traces = _trace(state, "Finalization", [f"Wrote {parsed_input_path}."])
    trace_payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_name": state.get("source_name"),
        "source_hash": state.get("source_hash"),
        "cache_hit": state.get("cache_hit"),
        "cache_path": state.get("cache_path"),
        "status": "completed",
        "step_traces": traces,
        "outputs": {
            "parsed_input": str(parsed_input_path),
            "affidavit_docx": state.get("docx_path"),
            "affidavit_markdown": state.get("md_path"),
            "evaluation_json": state.get("json_path"),
            "evaluation_markdown": state.get("evaluation_md_path"),
        },
    }
    (ARTIFACTS_DIR / "execution_trace.json").write_text(json.dumps(trace_payload, indent=2), encoding="utf-8")
    return {
        "parsed_input_path": str(parsed_input_path),
        "step_traces": traces,
        "current_step": "Completed",
        "status": "completed",
    }


def build_legal_doc_agent_graph():
    workflow = StateGraph(AgentWorkflowState)
    workflow.add_node("extract_entities", extract_entities)
    workflow.add_node("validate_entities", validate_entities)
    workflow.add_node("map_content", map_content)
    workflow.add_node("generate_document", generate_document)
    workflow.add_node("evaluate_document", evaluate_document)
    workflow.add_node("finalize_run", finalize_run)
    workflow.set_entry_point("extract_entities")
    workflow.add_edge("extract_entities", "validate_entities")
    workflow.add_edge("validate_entities", "map_content")
    workflow.add_edge("map_content", "generate_document")
    workflow.add_edge("generate_document", "evaluate_document")
    workflow.add_edge("evaluate_document", "finalize_run")
    workflow.add_edge("finalize_run", END)
    return workflow.compile()

def visualize_workflow_graph(workflow):
    """Return the rendered workflow graph for display after a UI button click."""
    if workflow is None:
        workflow = build_legal_doc_agent_graph()
    return workflow.get_graph().draw_mermaid_png()