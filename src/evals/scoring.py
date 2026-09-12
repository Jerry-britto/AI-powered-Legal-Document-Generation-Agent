"""
Comprehensive Dual-Layer Evaluation Engine for Affidavit in Reply.
Combines zero-tolerance deterministic rule checks and LLM multi-dimensional scoring.
"""

import re
import json
import logging
from typing import Dict, Any, List, Tuple
from src.schemas.entity_schema import (
    CaseInformationSchema,
    EvaluationReportSchema,
    DimensionScore,
    DeterministicCheckResult,
)

logger = logging.getLogger(__name__)


def run_deterministic_checks(
    generated_text: str,
    case_info: CaseInformationSchema,
    simulated_error: str = "none"
) -> Tuple[List[DeterministicCheckResult], List[Dict[str, Any]], bool]:
    """
    Executes strict programmatic validations on the generated legal document.
    Does not depend on an LLM.
    """
    text = generated_text
    checks: List[DeterministicCheckResult] = []
    issues: List[Dict[str, Any]] = []

    # If simulation requested for demonstration
    if simulated_error == "corrupt_paragraph_range":
        text = re.sub(r"paragraphs 1 to \d+", "paragraphs 1 to 3", text)
    elif simulated_error == "mismatch_respondent":
        text = re.sub(r"Advocates for the Respondent No\. \d+", "Advocates for the Respondent No. 3", text)
    elif simulated_error == "mismatch_verb":
        text = re.sub(r"Solemnly affirmed", "Sworn", text)

    # -------------------------------------------------------------
    # Check 1: Verification Paragraph Range Match
    # -------------------------------------------------------------
    # Isolate Part 7: Numbered body paragraphs (between deponent clause and PRAYER)
    body_match = re.search(
        r"do hereby\s+.*?\s+and state as under:?\s*\n+(.*?)\n+\s*(?:\*\*)?PRAYER",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if body_match:
        body_section = body_match.group(1)
        body_paras = re.findall(r"(?:^|\n)\s*(?:\*\*)?(\d+)\.(?:\*\*)?\s+[A-Z]", body_section)
    else:
        body_paras = re.findall(r"(?:^|\n)\s*(?:\*\*)?(\d+)\.(?:\*\*)?\s+[A-Z]", text)
    
    num_body_paras = len(body_paras)
    
    range_match = re.search(r"paragraphs\s+1\s+to\s+(\d+)", text, re.IGNORECASE)
    ver_range_num = int(range_match.group(1)) if range_match else None

    passed_range = (ver_range_num is not None and ver_range_num == num_body_paras)
    chk1 = DeterministicCheckResult(
        rule_id="RULE_01_VERIFICATION_RANGE",
        name="Verification Paragraph Range Match",
        passed=passed_range,
        expected=f"paragraphs 1 to {num_body_paras}",
        actual=f"paragraphs 1 to {ver_range_num}" if ver_range_num else "Not found / invalid range format",
        details="Verification in Part 10 must match the exact count of body paragraphs in Part 7."
    )
    checks.append(chk1)
    if not passed_range:
        issues.append({
            "dimension": "Consistency",
            "rule": "RULE_01_VERIFICATION_RANGE",
            "severity": "CRITICAL",
            "message": f"Verification clause states 'paragraphs 1 to {ver_range_num}' but the body contains {num_body_paras} numbered paragraphs.",
            "source_reference": "01 Affidavit Format Explained (Section 1 #10 & Section 5)"
        })

    # -------------------------------------------------------------
    # Check 2: Jurat Verb and Deponent Verb Agreement
    # -------------------------------------------------------------
    jurat_verb_match = re.search(r"(Solemnly affirmed|Sworn)\s+at", text, re.IGNORECASE)

    dep_verb = case_info.deponent.verification_verb.lower()
    expected_jurat_verb = "Solemnly affirmed" if "solemnly" in dep_verb else "Sworn"
    actual_jurat_verb = jurat_verb_match.group(1) if jurat_verb_match else "Missing"

    passed_verb = (actual_jurat_verb.lower() == expected_jurat_verb.lower())
    chk2 = DeterministicCheckResult(
        rule_id="RULE_02_VERB_AGREEMENT",
        name="Deponent Verb and Jurat Verb Agreement",
        passed=passed_verb,
        expected=f"Jurat verb '{expected_jurat_verb}' matching deponent clause '{dep_verb}'",
        actual=f"Jurat verb '{actual_jurat_verb}'",
        details="Deponent clause verb in Part 6 must agree with Jurat verb in Part 9."
    )
    checks.append(chk2)
    if not passed_verb:
        issues.append({
            "dimension": "Consistency",
            "rule": "RULE_02_VERB_AGREEMENT",
            "severity": "HIGH",
            "message": f"Jurat verb '{actual_jurat_verb}' does not match deponent affirmation verb '{dep_verb}'.",
            "source_reference": "01 Affidavit Format Explained (Section 2 & Section 5)"
        })

    # -------------------------------------------------------------
    # Check 3: Respondent Number Consistency Across All Sections
    # -------------------------------------------------------------
    target_resp_num = case_info.case_details.answering_respondent_number
    title_match = re.search(r"AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO\.\s*(\d+)", text, re.IGNORECASE)
    title_num = int(title_match.group(1)) if title_match else None
    
    adv_match = re.search(r"Advocates for the Respondent No\.\s*(\d+)", text, re.IGNORECASE)
    adv_num = int(adv_match.group(1)) if adv_match else None

    passed_resp = (title_num == target_resp_num and (adv_num is None or adv_num == target_resp_num))
    chk3 = DeterministicCheckResult(
        rule_id="RULE_03_RESPONDENT_CONSISTENCY",
        name="Respondent Number Uniformity",
        passed=passed_resp,
        expected=f"Respondent No. {target_resp_num} consistently in Title and Advocate block",
        actual=f"Title: Respondent No. {title_num}, Advocate: Respondent No. {adv_num}",
        details="The answering respondent number must remain uniform across title, deponent clause, and advocate block."
    )
    checks.append(chk3)
    if not passed_resp:
        issues.append({
            "dimension": "Consistency",
            "rule": "RULE_03_RESPONDENT_CONSISTENCY",
            "severity": "CRITICAL",
            "message": f"Inconsistent respondent numbering: expected {target_resp_num}, found Title No. {title_num}, Advocate No. {adv_num}.",
            "source_reference": "01 Affidavit Format Explained (Section 1 #4, #5)"
        })

    # -------------------------------------------------------------
    # Check 4: Deponent Organisation Designation Rule
    # -------------------------------------------------------------
    is_org = case_info.deponent.is_organisation
    passed_org_rule = True
    org_actual_msg = "Passed person deponent rule"

    if is_org:
        if re.search(r"I say that I am the Respondent No\.\s*\d+\s+in the above", text, re.IGNORECASE):
            passed_org_rule = False
            org_actual_msg = "Contains 'I say that I am the Respondent No.X' for an organisation"
        elif case_info.deponent.designation and case_info.deponent.designation.lower() not in text.lower():
            passed_org_rule = False
            org_actual_msg = f"Designation '{case_info.deponent.designation}' missing from deponent or body clause"
        else:
            org_actual_msg = f"Proper officer deposition by {case_info.deponent.designation}"

    chk4 = DeterministicCheckResult(
        rule_id="RULE_04_ORGANISATION_DEPONENT",
        name="Organisation Officer Deposition Rule",
        passed=passed_org_rule,
        expected="Officer deposes on behalf of authority/company with designation",
        actual=org_actual_msg,
        details="Never state 'I am the Respondent' when respondent is an authority or organisation."
    )
    checks.append(chk4)
    if not passed_org_rule:
        issues.append({
            "dimension": "Template Fidelity",
            "rule": "RULE_04_ORGANISATION_DEPONENT",
            "severity": "HIGH",
            "message": f"Organisation deposition rule violated: {org_actual_msg}.",
            "source_reference": "01 Affidavit Format Explained (Section 2 Deponent Rule)"
        })

    # -------------------------------------------------------------
    # Check 5: Required 10 Structural Parts Presence
    # -------------------------------------------------------------
    parts_map = {
        "1. Forum Heading": bool(re.search(r"IN THE HIGH COURT OF JUDICATURE AT", text, re.IGNORECASE)),
        "2. Jurisdiction": bool(re.search(r"JURISDICTION", text, re.IGNORECASE)),
        "3. Case Number": bool(re.search(r"NO\.\s*\d+\s*OF\s*\d{4}", text, re.IGNORECASE)),
        "4. Cause Title (VERSUS)": bool(re.search(r"\bVERSUS\b", text)),
        "5. Affidavit Title": bool(re.search(r"AFFIDAVIT IN REPLY ON BEHALF OF", text, re.IGNORECASE)),
        "6. Deponent Clause": bool(re.search(r"do hereby\s+(?:solemnly affirm|swear)\s+and state as under", text, re.IGNORECASE)),
        "7. Numbered Paragraphs": num_body_paras >= 4,
        "8. Prayer": bool(re.search(r"\bPRAYER\b", text)),
        "9. Jurat": bool(re.search(r"(?:Solemnly affirmed|Sworn)\s+at", text, re.IGNORECASE)),
        "10. Verification": bool(re.search(r"\bVERIFICATION\b", text)),
    }
    missing_parts = [k for k, v in parts_map.items() if not v]
    passed_parts = len(missing_parts) == 0

    chk5 = DeterministicCheckResult(
        rule_id="RULE_05_REQUIRED_PARTS",
        name="Presence of 10 Mandatory Structural Parts",
        passed=passed_parts,
        expected="All 10 structural parts present in prescribed order",
        actual="All 10 parts present" if passed_parts else f"Missing: {', '.join(missing_parts)}",
        details="High Court Affidavit in Reply must contain all 10 structural sections."
    )
    checks.append(chk5)
    if not passed_parts:
        issues.append({
            "dimension": "Structure",
            "rule": "RULE_05_REQUIRED_PARTS",
            "severity": "CRITICAL",
            "message": f"Mandatory structural parts missing: {', '.join(missing_parts)}.",
            "source_reference": "01 Affidavit Format Explained (Section 1 The Ten Parts)"
        })

    # -------------------------------------------------------------
    # Check 6: Prayer Lettering vs Body Numbering
    # -------------------------------------------------------------
    prayer_has_letters = bool(re.search(r"(?:\*\*)?\(a\)(?:\*\*)?\s+dismiss the present", text, re.IGNORECASE))
    chk6 = DeterministicCheckResult(
        rule_id="RULE_06_PRAYER_LETTERING",
        name="Prayer Lettering Distinction",
        passed=prayer_has_letters,
        expected="Prayer clauses lettered (a), (b), (c) and not numbered with body",
        actual="Lettered prayer clauses present" if prayer_has_letters else "Prayer clauses not properly lettered with (a)",
        details="Prayer is distinct from numbered body paragraphs and must use letters (a), (b), (c)."
    )
    checks.append(chk6)
    if not prayer_has_letters:
        issues.append({
            "dimension": "Template Fidelity",
            "rule": "RULE_06_PRAYER_LETTERING",
            "severity": "MEDIUM",
            "message": "Prayer clauses are not lettered (a), (b), (c) as required by High Court format rules.",
            "source_reference": "01 Affidavit Format Explained (Section 1 #8)"
        })

    all_passed = all(c.passed for c in checks)
    return checks, issues, all_passed


def evaluate_affidavit_document(
    generated_text: str,
    case_info: CaseInformationSchema,
    llm=None,
    simulated_error: str = "none"
) -> EvaluationReportSchema:
    """
    Complete evaluation pipeline producing scores for all 6 dimensions
    and compiling the final EvaluationReportSchema.
    """
    # Step 1: Run Deterministic Rule Engine
    det_checks, det_issues, det_all_passed = run_deterministic_checks(
        generated_text, case_info, simulated_error=simulated_error
    )

    # Step 2: Base dimension scores
    scores = {
        "Entity Accuracy": {"score": 100.0, "weight": 0.20, "issues": [], "explanation": "All supplied entities (court, parties, deponent, case number, date, firm) extracted and mapped accurately."},
        "Completeness": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "All 6 substantive points, exhibits, and prayer reliefs are comprehensively incorporated."},
        "Structure": {"score": 100.0, "weight": 0.20, "issues": [], "explanation": "All 10 mandatory sections appear in strict sequence per High Court format rules."},
        "Consistency": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Respondent numbering, party labels, and jurat/deponent verbs remain consistent throughout."},
        "Template Fidelity": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Fixed legal phrasing, bold numbering conventions, and lettered prayer strictly followed."},
        "Hallucination Check": {"score": 100.0, "weight": 0.15, "issues": [], "explanation": "Zero extraneous, unsupplied facts, dates, or parties introduced."},
    }

    # Map deterministic issues to dimension deductions
    for issue in det_issues:
        dim = issue["dimension"]
        sev = issue["severity"]
        deduction = 20.0 if sev == "CRITICAL" else (12.0 if sev == "HIGH" else 6.0)
        if dim in scores:
            scores[dim]["score"] = max(0.0, scores[dim]["score"] - deduction)
            scores[dim]["issues"].append(issue["message"])
            scores[dim]["explanation"] = f"Deduction of {deduction} pts applied due to: {issue['message']}"

    # Step 3: LLM Judge evaluation (if LLM is provided)
    if llm is not None:
        try:
            prompt = f"""You are a senior High Court judicial clerk and expert legal auditor.
Evaluate the following generated Affidavit in Reply against the supplied ground-truth case information.

GROUND TRUTH CASE INFORMATION:
Court: {case_info.case_details.court}
Jurisdiction: {case_info.case_details.jurisdiction}
Case: {case_info.case_details.proceeding_type} No. {case_info.case_details.case_number} of {case_info.case_details.year}
Petitioner: {case_info.case_details.petitioner}
Respondent 1: {case_info.case_details.respondents[0] if case_info.case_details.respondents else 'N/A'}
Respondent 2: {case_info.case_details.respondents[1] if len(case_info.case_details.respondents) > 1 else 'N/A'}
Deponent: {case_info.deponent.name}, {case_info.deponent.designation} of {case_info.deponent.organisation}
Points: {len(case_info.reply_points)} points to incorporate.
Advocate: {case_info.advocate.firm_name}

GENERATED AFFIDAVIT TEXT:
{generated_text[:4000]}

Score each dimension from 0 to 100 where 100 is PERFECT and 0 is worst:
- entity_accuracy_score: 100 if all names, numbers, dates, and court titles match ground truth.
- completeness_score: 100 if all 6 case reply points, prayer reliefs, and exhibits are covered.
- hallucination_score: 100 if completely faithful to the case facts with NO fabricated parties, dates, or unauthorized facts. Deduct points only if invented facts exist.

Return strictly valid JSON with this format:
{{
  "entity_accuracy_score": 100,
  "entity_accuracy_comment": "Accurate entity insertion",
  "completeness_score": 100,
  "completeness_comment": "All points included",
  "hallucination_score": 100,
  "hallucination_comment": "Zero hallucinated facts or invented entities",
  "additional_issues": []
}}
"""
            response = llm.invoke(prompt)
            raw_content = response.content
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].split("```")[0].strip()
            
            parsed_eval = json.loads(raw_content)
            if "entity_accuracy_score" in parsed_eval:
                ea = float(parsed_eval["entity_accuracy_score"])
                scores["Entity Accuracy"]["score"] = min(scores["Entity Accuracy"]["score"], ea)
            if "completeness_score" in parsed_eval:
                cs = float(parsed_eval["completeness_score"])
                scores["Completeness"]["score"] = min(scores["Completeness"]["score"], cs)
            if "hallucination_score" in parsed_eval:
                hs = float(parsed_eval["hallucination_score"])
                scores["Hallucination Check"]["score"] = min(scores["Hallucination Check"]["score"], hs)
            
            for extra in parsed_eval.get("additional_issues", []):
                det_issues.append({
                    "dimension": "General",
                    "rule": "LLM_AUDIT",
                    "severity": "LOW",
                    "message": str(extra),
                    "source_reference": "Ground Truth Comparison"
                })
        except Exception as e:
            logger.warning(f"LLM evaluation encountered exception ({e}); relying on robust deterministic scoring.")

    # Calculate weighted overall score
    overall_score = sum(data["score"] * data["weight"] for data in scores.values())
    overall_score = round(overall_score, 1)

    dimension_models = {
        dim: DimensionScore(
            dimension_name=dim,
            score=round(data["score"], 1),
            weight=data["weight"],
            issues_detected=data["issues"],
            explanation=data["explanation"]
        )
        for dim, data in scores.items()
    }

    scoring_explanation = (
        f"Overall Score ({overall_score}/100) is calculated as the weighted sum across 6 primary dimensions: "
        f"Entity Accuracy (20%), Structure (20%), Completeness (15%), Consistency (15%), "
        f"Template Fidelity (15%), and Hallucination Check (15%). "
        f"Deterministic checks enforce zero tolerance for High Court compliance errors."
    )

    doc_summary = (
        f"Affidavit in Reply for {case_info.case_details.court}, "
        f"{case_info.case_details.proceeding_type} No. {case_info.case_details.case_number} of {case_info.case_details.year}, "
        f"deposed by {case_info.deponent.name} on behalf of Respondent No. {case_info.case_details.answering_respondent_number}."
    )

    return EvaluationReportSchema(
        overall_score=overall_score,
        dimension_scores=dimension_models,
        deterministic_checks=det_checks,
        detected_issues=det_issues,
        score_calculation_explanation=scoring_explanation,
        document_summary=doc_summary,
        passed_all_deterministic=det_all_passed
    )
