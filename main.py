"""
Entry point for AI-Powered Legal Document Generation & Evaluation Agent.
Runs the complete LangGraph workflow on Case Information and outputs artifacts.
"""

import sys
import logging
from pathlib import Path
from src.graph.agent_worfklow import build_legal_doc_agent_graph
from src.utils.parser_utils import ingest_case_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_agent(input_file: str, provider: str = "groq", simulated_error: str = "none"):
    logger.info("Initializing Legal Document Generation Agent Pipeline...")
    input_path = Path(input_file)
    raw_text, source_meta = ingest_case_document(input_path.read_bytes(), input_path.name)

    graph = build_legal_doc_agent_graph()
    initial_state = {
        "raw_document_text": raw_text,
        **source_meta,
        "llm_provider": provider,
        "simulated_error": simulated_error,
        "current_step": "Starting Pipeline",
        "status": "initialized"
    }

    final_state = graph.invoke(initial_state)

    print("\n=======================================================")
    print("           LEGAL DOCUMENT GENERATION COMPLETED         ")
    print("=======================================================")
    print(f"Status: {final_state.get('status')}")
    print(f"Generated DOCX: {final_state.get('docx_path')}")
    print(f"Generated JSON: {final_state.get('json_path')}")
    print(f"Generated MD:   {final_state.get('md_path')}")
    print(f"Evaluation:     {final_state.get('evaluation_md_path')}")
    
    report = final_state.get("evaluation_report")
    if report:
        print("\n---------------- EVALUATION SCORECARD ----------------")
        print(f"OVERALL SCORE: {report.overall_score}/100")
        print("DIMENSION BREAKDOWN:")
        for dim, ds in report.dimension_scores.items():
            print(f" - {dim:20s}: {ds.score:5.1f}/100 (weight {int(ds.weight*100)}%)")
        print("\nDETERMINISTIC CHECKS:")
        for dc in report.deterministic_checks:
            mark = "PASS" if dc.passed else "FAIL"
            print(f" [{mark}] {dc.name:35s}: {dc.actual}")
    print("=======================================================\n")
    return final_state


if __name__ == "__main__":
    provider_arg = sys.argv[1] if len(sys.argv) > 1 else "groq"
    sim_arg = sys.argv[2] if len(sys.argv) > 2 else "none"
    if len(sys.argv) < 4:
        raise SystemExit("Usage: python main.py <provider> <simulated_error> <input_file>")
    run_agent(sys.argv[3], provider=provider_arg, simulated_error=sim_arg)
