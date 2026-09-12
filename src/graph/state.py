"""
State definition for the Legal Document Generation & Evaluation Agent.
"""

from typing import TypedDict, Optional, Dict, Any, List
from src.schemas.entity_schema import CaseInformationSchema, EvaluationReportSchema


class AgentWorkflowState(TypedDict, total=False):
    # Inputs
    raw_document_text: str
    source_name: str
    source_hash: str
    cache_hit: bool
    cache_path: str
    llm_provider: str  # "groq" or "gemini"
    llm_model: Optional[str]
    simulated_error: str  # "none", "corrupt_paragraph_range", "mismatch_respondent", "mismatch_verb"

    # Stage 1 & 2: Extraction & Structured IR
    intermediate_data: Optional[CaseInformationSchema]
    pre_generation_errors: List[str]

    # Stage 3: Content & Move Mapping
    mapped_sections: Dict[str, Any]

    # Stage 4: Generated Affidavit
    generated_text: str
    docx_path: Optional[str]
    json_path: Optional[str]
    md_path: Optional[str]
    evaluation_md_path: Optional[str]
    parsed_input_path: Optional[str]

    # Stage 5: Evaluation
    evaluation_report: Optional[EvaluationReportSchema]

    # Progress tracking & Detailed Step Traces
    current_step: str
    status: str
    error_message: Optional[str]
    step_traces: List[Dict[str, Any]]
