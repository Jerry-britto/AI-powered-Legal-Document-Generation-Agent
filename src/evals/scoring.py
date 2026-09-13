"""Reference- and case-driven evaluation for generated affidavits."""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from src.schemas.schema_info import (
    CaseInformationSchema,
    DeterministicCheckResult,
    DimensionScore,
    EvaluationReportSchema,
)

logger = logging.getLogger(__name__)

# HELPER UTILITY FUNCTIONS
def _message_content_to_text(content: Any) -> str:
    """Normalize LangChain message content across string and block formats."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _present(text: str, value: str) -> bool:
    expected = _normalise(value)
    return bool(expected) and expected in _normalise(text)


def _content_coverage(paragraph: str, content: str) -> bool:
    """Require the paragraph to preserve the substance of a supplied bullet."""
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", _normalise(content))
        if len(token) > 2
    }
    if not tokens:
        return True
    paragraph_tokens = set(re.findall(r"[a-z0-9]+", _normalise(paragraph)))
    overlap = len(tokens & paragraph_tokens) / len(tokens)
    return overlap >= 0.4 or len(tokens & paragraph_tokens) >= 3


def _body_paragraphs(text: str) -> List[Tuple[int, str]]:
    """Find numbered paragraphs without assuming a particular paragraph count."""
    body = text
    start = re.search(r"(?:state|say)\s+as\s+under\s*:?", text, re.IGNORECASE)
    end = re.search(r"\bPRAYER\b", text, re.IGNORECASE)
    if start and end and start.end() < end.start():
        body = text[start.end():end.start()]
    return [
        (int(number), content.strip())
        for number, content in re.findall(
            r"(?ms)^\s*(?:\*{0,2})?(\d+)\s*[.)](?:\*{0,2})?\s*(.+?)(?=^\s*(?:\*{0,2})?\d+\s*[.)]|\Z)",
            body,
            re.DOTALL,
        )
    ]


def _verification_range(text: str) -> str | None:
    match = re.search(
        r"\bparagraphs?\s+(\d+)\s+(?:to|through|-)\s+(\d+)\b",
        text,
        re.IGNORECASE,
    )
    return f"{match.group(1)} to {match.group(2)}" if match else None


def _add_check(
    checks: List[DeterministicCheckResult],
    issues: List[Dict[str, Any]],
    rule_id: str,
    name: str,
    passed: bool,
    expected: str,
    actual: str,
    details: str,
    dimension: str,
    severity: str = "HIGH",
) -> None:
    checks.append(DeterministicCheckResult(
        rule_id=rule_id,
        name=name,
        passed=passed,
        expected=expected,
        actual=actual,
        details=details,
    ))
    if not passed:
        issues.append({
            "dimension": dimension,
            "rule": rule_id,
            "severity": severity,
            "message": f"{name}: expected {expected}; found {actual}.",
            "source_reference": "Extracted case information and generated affidavit",
        })


def run_deterministic_checks(
    generated_text: str,
    case_info: CaseInformationSchema,
    simulated_error: str = "none",
) -> Tuple[List[DeterministicCheckResult], List[Dict[str, Any]], bool]:
    """Validate the output against the current case, not a sample case."""
    text = generated_text
    if simulated_error == "corrupt_paragraph_range":
        text = re.sub(r"paragraphs?\s+1\s+(?:to|through|-)\s+\d+", "paragraphs 1 to 1", text, count=1, flags=re.IGNORECASE)
    elif simulated_error == "mismatch_respondent":
        target = str(case_info.case_details.answering_respondent_number)
        text = re.sub(
            rf"((?:on\s+behalf\s+of|advocates?\s+for\s+the|of\s+the)\s+(?:the\s+)?respondent\s+no\.?)\s*{re.escape(target)}",
            r"\1 999",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    elif simulated_error == "mismatch_verb":
        text = re.sub(r"\bSolemnly affirmed\b", "Sworn", text, count=1, flags=re.IGNORECASE)

    checks: List[DeterministicCheckResult] = []
    issues: List[Dict[str, Any]] = []
    paragraphs = _body_paragraphs(text)
    expected_count = len(case_info.reply_points)
    actual_numbers = [number for number, _ in paragraphs]
    expected_numbers = list(range(1, expected_count + 1))

    _add_check(
        checks, issues, "CASE_REPLY_POINT_COVERAGE", "Reply point coverage",
        len(paragraphs) == expected_count and actual_numbers == expected_numbers,
        f"exactly {expected_count} sequential numbered reply paragraphs",
        f"{len(paragraphs)} paragraphs numbered {actual_numbers}",
        "The generated body must represent the number and sequence of reply points extracted from this case.",
        "Completeness", "CRITICAL",
    )

    missing_content = []
    paragraphs_by_number = dict(paragraphs)
    for point in case_info.reply_points:
        paragraph = paragraphs_by_number.get(point.point_number, "")
        for bullet in point.content_bullets:
            if not _content_coverage(paragraph, bullet):
                missing_content.append(f"Point {point.point_number}: {bullet}")
    _add_check(
        checks, issues, "CASE_REPLY_CONTENT_COVERAGE", "Reply content coverage",
        not missing_content,
        "Every extracted reply averment is substantively represented",
        "Missing: " + "; ".join(missing_content) if missing_content else "All extracted reply averments represented",
        "Paragraph counts alone are insufficient; each supplied reply bullet must survive drafting.",
        "Completeness", "HIGH",
    )

    verification_range = _verification_range(text)
    expected_range = f"1 to {len(paragraphs)}"
    _add_check(
        checks, issues,         "RULE_01_VERIFICATION_RANGE", "Verification paragraph range",
        verification_range is None or verification_range.lower() == expected_range.lower(),
        f"paragraphs {expected_range} when a range is stated",
        verification_range or "No paragraph range stated",
        "If the document states a verification range, it must match the generated body count.",
        "Consistency", "CRITICAL",
    )

    target_number = str(case_info.case_details.answering_respondent_number)
    context_numbers = re.findall(
        r"(?:on\s+behalf\s+of|advocates?\s+for\s+the|of\s+the)\s+"
        r"(?:the\s+)?respondent\s+no\.?\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    number_consistent = bool(context_numbers) and all(number == target_number for number in context_numbers)
    _add_check(
        checks, issues,         "RULE_03_RESPONDENT_CONSISTENCY", "Answering respondent consistency",
        number_consistent,
        f"Respondent No. {target_number} wherever a respondent number is used",
        ", ".join(f"Respondent No. {number}" for number in context_numbers) or "No answering-respondent context found",
        "The respondent number is taken from the current extracted case, never from a fixed sample.",
        "Consistency", "CRITICAL",
    )

    caption_ok = bool(re.search(
        rf"{re.escape(case_info.case_details.petitioner)}\s+\.\.\.\s*Petitioner.*?"
        rf"{re.escape(case_info.case_details.answering_respondent_name)}\s+\.\.\.\s*Respondent\s+No\.?\s*{target_number}",
        text,
        re.IGNORECASE | re.DOTALL,
    ))
    _add_check(
        checks, issues, "CASE_CAPTION_ROLES", "Caption party-role consistency",
        caption_ok,
        "Petitioner and answering respondent appear in their extracted caption roles",
        "Caption roles match extracted parties" if caption_ok else "Caption party role/name mismatch",
        "Entity correctness includes the relationship between a party name and its caption role.",
        "Entity Accuracy", "CRITICAL",
    )

    deponent_context_ok = bool(
        re.search(
            rf"{re.escape(case_info.deponent.name)}.*?"
            rf"{re.escape(case_info.case_details.answering_respondent_name)}",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        or re.search(
            rf"{re.escape(case_info.deponent.name)}.*?"
            rf"respondent\s+no\.?\s*{target_number}",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    _add_check(
        checks, issues, "CASE_DEPONENT_ROLE", "Deponent role consistency",
        deponent_context_ok,
        "Deponent is identified as representing the answering respondent",
        "Deponent/respondent relationship present" if deponent_context_ok else "Deponent/respondent relationship missing",
        "The deponent's identity must be connected to the extracted answering respondent.",
        "Entity Accuracy", "HIGH",
    )

    deponent = case_info.deponent
    deponent_values = [deponent.name]
    if deponent.designation:
        deponent_values.append(deponent.designation)
    missing_deponent = [value for value in deponent_values if not _present(text, value)]
    address_tokens = [
        token for token in re.findall(r"[a-z0-9]+", _normalise(deponent.address))
        if len(token) > 2
    ]
    if address_tokens and not any(_present(text, token) for token in address_tokens):
        missing_deponent.append(deponent.address)
    _add_check(
        checks, issues, "CASE_DEPONENT_DATA", "Deponent data coverage",
        not missing_deponent,
        "Name, address, and supplied designation present",
        f"Missing: {', '.join(missing_deponent)}" if missing_deponent else "All supplied deponent data present",
        "Every supplied deponent field required for drafting must survive generation.",
        "Entity Accuracy", "HIGH",
    )

    required_values = [
        case_info.case_details.court,
        case_info.case_details.case_number,
        case_info.case_details.year,
        case_info.case_details.petitioner,
        case_info.case_details.answering_respondent_name,
        case_info.attestation.place,
        case_info.advocate.firm_name,
    ]
    missing_entities = [value for value in required_values if not _present(text, value)]
    if not (
        _present(text, case_info.attestation.date_raw)
        or _present(text, case_info.attestation.date_ordinal)
    ):
        missing_entities.append(
            f"{case_info.attestation.date_raw} / {case_info.attestation.date_ordinal}"
        )
    _add_check(
        checks, issues, "CASE_ENTITY_COVERAGE", "Case entity coverage",
        not missing_entities,
        "All required extracted case entities present",
        f"Missing: {', '.join(missing_entities)}" if missing_entities else "All required entities present",
        "Required values are derived from the current CaseInformationSchema.",
        "Entity Accuracy", "CRITICAL",
    )

    if case_info.deponent.organisation:
        _add_check(
            checks, issues, "CASE_DEPONENT_ORGANISATION", "Deponent organisation coverage",
            _present(text, case_info.deponent.organisation),
            "Supplied deponent organisation present",
            case_info.deponent.organisation if _present(text, case_info.deponent.organisation) else "Organisation missing",
            "An organisation deponent must identify the organisation represented.",
            "Entity Accuracy", "HIGH",
        )

    prayers = case_info.prayer.items
    prayer_start = re.search(r"\bPRAYER\b", text, re.IGNORECASE)
    prayer_text = text[prayer_start.start():] if prayer_start else ""
    prayer_markers = re.findall(r"(?m)^\s*(?:\*{0,2})?\(([a-z]+)\)(?:\*{0,2})?\s+", prayer_text, re.IGNORECASE)
    prayer_complete = bool(prayer_start) and len(prayer_markers) == len(prayers)
    _add_check(
        checks, issues, "CASE_PRAYER_COVERAGE", "Prayer coverage",
        prayer_complete,
        f"PRAYER section with {len(prayers)} lettered item(s)",
        f"{len(prayer_markers)} lettered item(s)" if prayer_start else "PRAYER section missing",
        "Prayer count and presence are derived from this case's extracted prayer items.",
        "Completeness", "HIGH",
    )

    required_sections = {
        "court heading": case_info.case_details.court,
        "case number": case_info.case_details.case_number,
        "affidavit title": "AFFIDAVIT",
        "deponent clause": "state as under",
        "prayer": "PRAYER",
        "verification": "VERIFICATION",
    }
    missing_sections = [name for name, marker in required_sections.items() if not _present(text, marker)]
    _add_check(
        checks, issues, "REFERENCE_SECTION_PRESENCE", "Required affidavit sections",
        not missing_sections,
        "Court, case, affidavit, deponent, prayer, and verification sections",
        f"Missing: {', '.join(missing_sections)}" if missing_sections else "All required sections present",
        "The section checklist is document-type specific and can be replaced by analyzed reference rules.",
        "Structure", "CRITICAL",
    )

    affirming = "solemnly" in deponent.verification_verb.lower()
    deponent_match = re.search(
        r"do\s+hereby\s+(solemnly\s+affirm|swear(?:\s+and\s+affirm)?)",
        text,
        re.IGNORECASE,
    )
    jurat_match = re.search(
        r"\b(solemnly\s+affirmed|sworn)\s+(?:at|on)\b",
        text,
        re.IGNORECASE,
    )
    found_verbs = [match for match in (deponent_match, jurat_match) if match]
    deponent_verb = deponent_match.group(1).lower() if deponent_match else ""
    jurat_verb = jurat_match.group(1).lower() if jurat_match else ""
    verb_ok = bool(deponent_match and jurat_match) and (
        ("solemnly" in deponent_verb) == ("solemnly" in jurat_verb) == affirming
    )
    _add_check(
        checks, issues,         "RULE_02_VERB_AGREEMENT", "Attestation verb consistency",
        verb_ok,
        "Attestation verb agrees with extracted deponent verification verb",
        f"deponent={deponent_verb or 'missing'}, jurat={jurat_verb or 'missing'}",
        "The expected verb is derived from the current deponent data.",
        "Consistency", "HIGH",
    )

    duplicate_exhibit = bool(
        re.search(
            r"(EXHIBIT[-\s]*['‘\"]?[A-Z]['’\"]?\.?)\s+\1",
            text,
            re.IGNORECASE,
        )
    )
    _add_check(
        checks, issues, "RULE_04_EXHIBIT_REFERENCE", "Exhibit reference formatting",
        not duplicate_exhibit,
        "Each exhibit reference appears once in its paragraph",
        "Duplicate exhibit reference detected" if duplicate_exhibit else "No duplicate exhibit references",
        "Repeated exhibit markers are a template/drafting defect, not a case-entity failure.",
        "Template Fidelity", "LOW",
    )

    prayer_redundancy = bool(
        re.search(
            r"may\s+be\s+pleased\s+to\s*:?\s*\(?[a-z]+\)?\s+"
            r"(?:the\s+)?(?:answering\s+)?respondent\s+no\.?\s*\d+\s+prays",
            prayer_text,
            re.IGNORECASE,
        )
    )
    _add_check(
        checks, issues, "RULE_05_PRAYER_FRAMING", "Prayer framing",
        not prayer_redundancy,
        "Prayer items follow the prayer preamble without repeating the party's prayer verb",
        "Redundant respondent prayer wording" if prayer_redundancy else "Prayer framing is consistent",
        "The prayer preamble and lettered clauses must form one grammatical construction.",
        "Template Fidelity", "LOW",
    )

    return checks, issues, all(check.passed for check in checks)


def evaluate_affidavit_document(
    generated_text: str,
    case_info: CaseInformationSchema,
    llm=None,
    simulated_error: str = "none",
) -> EvaluationReportSchema:
    checks, issues, deterministic_passed = run_deterministic_checks(
        generated_text, case_info, simulated_error=simulated_error
    )
    scores = {
        "Entity Accuracy": {"score": 100.0, "weight": 0.20, "issues": [], "explanation": "Compared against entities extracted from the current case."},
        "Completeness": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Compared against this case's reply points and prayer items."},
        "Structure": {"score": 100.0, "weight": 0.20, "issues": [], "explanation": "Checked against the affidavit section contract."},
        "Consistency": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Checked against relationships in the current case data."},
        "Template Fidelity": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Checked against the configured affidavit document type and section conventions."},
        "Hallucination Check": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Audits unsupported facts and claims against the extracted case."},
    }
    deductions = {"CRITICAL": 20.0, "HIGH": 12.0, "MEDIUM": 6.0, "LOW": 3.0}
    deterministic_deductions = {dimension: 0.0 for dimension in scores}
    for issue in issues:
        dimension = issue["dimension"]
        if dimension in scores:
            deduction = deductions[issue["severity"]]
            scores[dimension]["score"] = max(0.0, scores[dimension]["score"] - deduction)
            deterministic_deductions[dimension] += deduction
            scores[dimension]["issues"].append(issue["message"])

    if llm is not None:
        try:
            prompt = f"""Evaluate this generated Affidavit in Reply against the supplied case data
and the affidavit conventions represented by the document structure.

Return ONLY valid JSON in this exact shape:
{{
  "dimension_scores": {{
    "Entity Accuracy": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}},
    "Completeness": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}},
    "Structure": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}},
    "Consistency": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}},
    "Template Fidelity": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}},
    "Hallucination Check": {{"score": 0-100, "issues": [{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "description": "..."}}]}}
  }}
}}

Assess all six dimensions. Do not use fixed sample values. Scores below 100 MUST
be supported by at least one issue in the same dimension. Do not penalize a
dimension for an issue belonging to another dimension. Check unsupported facts,
omissions, section/order/template deviations, inconsistent names/numbers/dates,
and grammar or formatting defects.

CASE DATA:
{case_info.model_dump_json()}

GENERATED DOCUMENT:
{generated_text}
"""
            raw = _message_content_to_text(llm.invoke(prompt).content)
            raw = raw.split("```json", 1)[-1].split("```", 1)[0].strip()
            parsed = json.loads(raw)
            
            llm_dimensions = parsed.get("dimension_scores", {})
            if isinstance(llm_dimensions, dict):
                for dimension, result in llm_dimensions.items():
                    if dimension not in scores or not isinstance(result, dict):
                        continue
                    raw_score = result.get("score")
                    raw_issues = result.get("issues", [])
                    try:
                        llm_score = float(raw_score)
                    except (TypeError, ValueError):
                        continue
                    if not 0 <= llm_score <= 100 or (llm_score < 100 and not raw_issues):
                        logger.warning(
                            "Ignoring unsupported LLM score for %s: score=%r issues=%r",
                            dimension, raw_score, raw_issues,
                        )
                        continue
                    normalized_findings = []
                    for finding in raw_issues:
                        if isinstance(finding, dict):
                            severity = str(finding.get("severity", "MEDIUM")).upper()
                            message = str(finding.get("description", finding))
                        else:
                            severity = "MEDIUM"
                            message = str(finding)
                        if severity not in deductions:
                            severity = "MEDIUM"
                        normalized_findings.append((severity, message))
                        issue = {
                            "dimension": dimension,
                            "rule": "LLM_CASE_AUDIT",
                            "severity": severity,
                            "message": message,
                            "source_reference": "Current case information and affidavit conventions",
                        }
                        issues.append(issue)
                        scores[dimension]["issues"].append(message)
                    finding_score = max(
                        0.0,
                        100.0 - sum(deductions[severity] for severity, _ in normalized_findings),
                    )
                    scores[dimension]["score"] = min(
                        scores[dimension]["score"], llm_score, finding_score
                    )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("LLM evaluation response was not valid JSON: %s", exc)

    dimensions = {
        name: DimensionScore(
            dimension_name=name,
            score=round(data["score"], 1),
            weight=data["weight"],
            issues_detected=data["issues"],
            explanation=data["explanation"],
        )
        for name, data in scores.items()
    }
    overall = round(sum(item.score * dimensions[name].weight for name, item in dimensions.items()), 1)
    readiness_reasons = [
        f"{issue['dimension']}: {issue['message']}"
        for issue in issues
    ]
    filing_ready = deterministic_passed and not issues
    readiness_status = "READY" if filing_ready else "NOT_READY"
    deduction_summary = ", ".join(
        f"{name} -{value:g}" for name, value in deterministic_deductions.items() if value
    ) or "none"
    return EvaluationReportSchema(
        overall_score=overall,
        dimension_scores=dimensions,
        deterministic_checks=checks,
        detected_issues=issues,
        score_calculation_explanation=(
            "Weighted score across six dimensions. Expectations are derived from the "
            "current extracted case; no sample-specific counts, respondent numbers, "
            "or prayer wording are used. Deterministic deductions: "
            f"{deduction_summary}. LLM scores are accepted only when supported by "
            "same-dimension findings and can only lower the deterministic baseline."
        ),
        document_summary=(
            f"Affidavit in Reply for {case_info.case_details.proceeding_type} "
            f"{case_info.case_details.case_number} of {case_info.case_details.year}."
        ),
        passed_all_deterministic=deterministic_passed,
        filing_ready=filing_ready,
        readiness_status=readiness_status,
        readiness_reasons=readiness_reasons,
    )
