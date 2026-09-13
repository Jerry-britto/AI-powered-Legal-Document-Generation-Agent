"""
Unit tests for deterministic validation rule engine.
"""

import json
import unittest
from src.schemas.schema_info import (
    CaseInformationSchema,
    CourtAndCaseDetails,
    DeponentDetails,
    ReplyPoint,
    PrayerDetails,
    AttestationDetails,
    AdvocateDetails,
)
from src.evals.scoring import evaluate_affidavit_document, run_deterministic_checks


class TestDeterministicValidation(unittest.TestCase):
    def setUp(self):
        self.case_info = CaseInformationSchema(
            case_details=CourtAndCaseDetails(
                document_type="Affidavit in Reply",
                court="IN THE HIGH COURT OF JUDICATURE AT BOMBAY",
                jurisdiction="ORDINARY ORIGINAL CIVIL JURISDICTION",
                proceeding_type="WRIT PETITION",
                case_number="1847",
                year="2026",
                petitioner="Sunrise Housing Private Limited",
                respondents=["State of Maharashtra", "Mumbai Metropolitan Region Development Authority"],
                filed_on_behalf_of="Respondent No. 2",
                answering_respondent_number=2,
                answering_respondent_name="Mumbai Metropolitan Region Development Authority"
            ),
            deponent=DeponentDetails(
                name="Arvind Rajan",
                designation="Deputy Metropolitan Commissioner",
                organisation="Mumbai Metropolitan Region Development Authority",
                address="Bandra East, Mumbai, Maharashtra",
                is_organisation=True,
                verification_verb="solemnly affirm"
            ),
            reply_points=[
                ReplyPoint(
                    point_number=1,
                    title="Filing",
                    content_bullets=["The deponent has perused a copy of the Writ Petition."],
                    move_type="IDENTITY_AND_PERUSAL",
                ),
                ReplyPoint(
                    point_number=2,
                    title="Denial",
                    content_bullets=["The deponent denies each and every allegation."],
                    move_type="BLANKET_DENIAL",
                ),
                ReplyPoint(
                    point_number=3,
                    title="Preliminary",
                    content_bullets=["The Writ Petition is misconceived."],
                    move_type="PRELIMINARY_POSITION",
                ),
                ReplyPoint(
                    point_number=4,
                    title="Denial of Averments",
                    content_bullets=["The averments are denied."],
                    move_type="SUBSTANTIVE_ANSWER",
                ),
                ReplyPoint(
                    point_number=5,
                    title="Relief",
                    content_bullets=["The Writ Petition deserves to be dismissed."],
                    move_type="CLOSING",
                ),
            ],
            prayer=PrayerDetails(items=["dismiss the present Writ Petition with costs;"]),
            attestation=AttestationDetails(place="Mumbai", date_raw="5 September 2026", date_ordinal="5th day of September 2026"),
            advocate=AdvocateDetails(firm_name="Rajan & Associates", acting_for="Respondent No. 2"),
        )

        self.valid_text = """
**IN THE HIGH COURT OF JUDICATURE AT BOMBAY**
**ORDINARY ORIGINAL CIVIL JURISDICTION**
**WRIT PETITION NO. 1847 OF 2026**

Sunrise Housing Private Limited ...Petitioner
VERSUS
1. State of Maharashtra ...Respondent No.1
2. Mumbai Metropolitan Region Development Authority ...Respondent No.2

AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO. 2

I, Arvind Rajan, having office at Bandra East, Mumbai, the Deputy Metropolitan Commissioner of the Respondent No.2 above named, do hereby solemnly affirm and state as under:

**1.** The deponent has perused a copy of the Writ Petition.
**2.** The deponent denies each and every allegation.
**3.** The Writ Petition is misconceived.
**4.** With reference to the averments, the averments are denied.
**5.** The Writ Petition deserves to be dismissed with costs.

PRAYER
I therefore respectfully pray that this Hon'ble Court may be pleased to:
**(a)** dismiss the present Writ Petition with costs;

Solemnly affirmed at Mumbai
On this 5th day of September 2026
Before Me                                                                DEPONENT

VERIFICATION
I, Arvind Rajan, the Deponent above named, do hereby verify that the contents of paragraphs 1 to 5 and the Prayer above are true and correct...
Verified at Mumbai on this 5th day of September 2026.
                                                                         DEPONENT
RAJAN & ASSOCIATES
Advocates for the Respondent No. 2.
"""

    def test_valid_document_passes_all_checks(self):
        checks, issues, all_passed = run_deterministic_checks(self.valid_text, self.case_info)
        self.assertTrue(all_passed, f"Valid document failed checks: {issues}")
        self.assertEqual(len(issues), 0)

    def test_corrupted_paragraph_range_fails(self):
        checks, issues, all_passed = run_deterministic_checks(
            self.valid_text, self.case_info, simulated_error="corrupt_paragraph_range"
        )
        self.assertFalse(all_passed)
        range_check = next(c for c in checks if c.rule_id == "RULE_01_VERIFICATION_RANGE")
        self.assertFalse(range_check.passed)

    def test_mismatched_respondent_fails(self):
        checks, issues, all_passed = run_deterministic_checks(
            self.valid_text, self.case_info, simulated_error="mismatch_respondent"
        )
        self.assertFalse(all_passed)
        resp_check = next(c for c in checks if c.rule_id == "RULE_03_RESPONDENT_CONSISTENCY")
        self.assertFalse(resp_check.passed)

    def test_mismatched_verb_fails(self):
        checks, issues, all_passed = run_deterministic_checks(
            self.valid_text, self.case_info, simulated_error="mismatch_verb"
        )
        self.assertFalse(all_passed)
        verb_check = next(c for c in checks if c.rule_id == "RULE_02_VERB_AGREEMENT")
        self.assertFalse(verb_check.passed)

    def test_extra_reply_paragraph_fails(self):
        extra_paragraph = self.valid_text.replace(
            "\nPRAYER",
            "\n**6.** This extra paragraph is not present in the extracted case.\n\nPRAYER",
        )
        checks, issues, all_passed = run_deterministic_checks(extra_paragraph, self.case_info)
        self.assertFalse(all_passed)
        coverage_check = next(c for c in checks if c.rule_id == "CASE_REPLY_POINT_COVERAGE")
        self.assertFalse(coverage_check.passed)

    def test_missing_reply_content_fails(self):
        missing_content = self.valid_text.replace(
            "The deponent has perused a copy of the Writ Petition.",
            "The deponent addresses the Court.",
        )
        checks, issues, all_passed = run_deterministic_checks(missing_content, self.case_info)
        self.assertFalse(all_passed)
        content_check = next(c for c in checks if c.rule_id == "CASE_REPLY_CONTENT_COVERAGE")
        self.assertFalse(content_check.passed)

    def test_template_defects_fail_and_block_readiness(self):
        defective_text = self.valid_text.replace(
            "The Writ Petition deserves to be dismissed with costs.",
            "The Writ Petition deserves to be dismissed with costs. "
            "A copy is marked as EXHIBIT-'A'. EXHIBIT-'A'.",
        ).replace(
            "**(a)** dismiss the present Writ Petition with costs;",
            "(a) Respondent No. 2 prays that the Writ Petition be dismissed with costs;",
        )
        report = evaluate_affidavit_document(defective_text, self.case_info)
        self.assertFalse(report.passed_all_deterministic)
        self.assertFalse(report.filing_ready)
        self.assertEqual(report.readiness_status, "NOT_READY")
        self.assertEqual(report.dimension_scores["Template Fidelity"].score, 94.0)
        self.assertEqual(len(report.readiness_reasons), 2)

    def test_llm_scores_all_dimensions_only_with_findings(self):
        dimensions = {
            name: {"score": 100, "issues": []}
            for name in (
                "Entity Accuracy",
                "Completeness",
                "Structure",
                "Consistency",
                "Template Fidelity",
                "Hallucination Check",
            )
        }
        dimensions["Template Fidelity"] = {
            "score": 94,
            "issues": [{"severity": "LOW", "description": "Minor style defect"}],
        }

        class FakeMessage:
            content = json.dumps({"dimension_scores": dimensions})

        class FakeLLM:
            def invoke(self, prompt):
                return FakeMessage()

        report = evaluate_affidavit_document(self.valid_text, self.case_info, FakeLLM())
        self.assertEqual(report.dimension_scores["Entity Accuracy"].score, 100.0)
        self.assertEqual(report.dimension_scores["Template Fidelity"].score, 94.0)
        self.assertEqual(report.overall_score, 99.1)

    def test_unsupported_llm_low_score_is_ignored(self):
        dimensions = {
            name: {"score": 1, "issues": []}
            for name in (
                "Entity Accuracy",
                "Completeness",
                "Structure",
                "Consistency",
                "Template Fidelity",
                "Hallucination Check",
            )
        }

        class FakeMessage:
            content = json.dumps({"dimension_scores": dimensions})

        class FakeLLM:
            def invoke(self, prompt):
                return FakeMessage()

        report = evaluate_affidavit_document(self.valid_text, self.case_info, FakeLLM())
        self.assertEqual(report.dimension_scores["Entity Accuracy"].score, 100.0)
        self.assertEqual(report.dimension_scores["Hallucination Check"].score, 100.0)


if __name__ == "__main__":
    unittest.main()
