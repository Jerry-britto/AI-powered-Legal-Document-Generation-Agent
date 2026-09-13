"""
Unit tests for Pydantic schema validation and entity extraction.
"""

import unittest
from pydantic import ValidationError
from src.schemas.schema_info import (
    CaseInformationSchema,
    CourtAndCaseDetails,
    DeponentDetails,
    ReplyPoint,
    PrayerDetails,
    AttestationDetails,
    AdvocateDetails,
)


class TestEntitySchema(unittest.TestCase):
    def test_valid_schema(self):
        schema = CaseInformationSchema(
            case_details=CourtAndCaseDetails(
                document_type="Affidavit in Reply",
                court="IN THE HIGH COURT OF JUDICATURE AT BOMBAY",
                jurisdiction="ORDINARY ORIGINAL CIVIL JURISDICTION",
                proceeding_type="WRIT PETITION",
                case_number="1847",
                year="2026",
                petitioner="Sunrise Housing Private Limited",
                respondents=["State of Maharashtra", "MMRDA"],
                filed_on_behalf_of="Respondent No. 2",
                answering_respondent_number=2,
                answering_respondent_name="MMRDA"
            ),
            deponent=DeponentDetails(
                name="Arvind Rajan",
                designation="Deputy Metropolitan Commissioner",
                organisation="MMRDA",
                address="Bandra East, Mumbai",
                is_organisation=True,
                verification_verb="solemnly affirm"
            ),
            reply_points=[
                ReplyPoint(point_number=1, title="Point 1", content_bullets=["b1"], move_type="IDENTITY_AND_PERUSAL")
            ],
            prayer=PrayerDetails(items=["dismiss the writ petition with costs"]),
            attestation=AttestationDetails(place="Mumbai", date_raw="5 September 2026", date_ordinal="5th day of September 2026"),
            advocate=AdvocateDetails(firm_name="Rajan & Associates", acting_for="Respondent No. 2")
        )
        self.assertEqual(schema.case_details.case_number, "1847")
        self.assertTrue(schema.deponent.is_organisation)

    def test_missing_designation_for_organisation_fails(self):
        # Deponent represents an authority/organisation but lacks designation
        with self.assertRaises(ValueError):
            CaseInformationSchema(
                case_details=CourtAndCaseDetails(
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
                    designation=None,  # Missing designation for organisation!
                    organisation="Mumbai Metropolitan Region Development Authority",
                    address="Bandra East, Mumbai",
                    is_organisation=True,
                    verification_verb="solemnly affirm"
                ),
                reply_points=[],
                prayer=PrayerDetails(items=[]),
                attestation=AttestationDetails(place="Mumbai", date_raw="5 Sept 2026", date_ordinal="5th day of September 2026"),
                advocate=AdvocateDetails(firm_name="Rajan & Associates", acting_for="Respondent No. 2")
            )


if __name__ == "__main__":
    unittest.main()
