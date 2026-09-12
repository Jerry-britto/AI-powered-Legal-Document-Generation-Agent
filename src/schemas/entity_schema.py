"""
Pydantic Schemas for Legal Entity Extraction, Content Mapping,
and Multi-Dimensional Document Evaluation.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class CourtAndCaseDetails(BaseModel):
    document_type: str = Field(default="Affidavit in Reply", description="Type of document")
    court: str = Field(..., description="Full court heading, e.g., 'IN THE HIGH COURT OF JUDICATURE AT BOMBAY'")
    jurisdiction: str = Field(..., description="Jurisdiction line ending in JURISDICTION, e.g., 'ORDINARY ORIGINAL CIVIL JURISDICTION'")
    proceeding_type: str = Field(..., description="Proceeding type, e.g., 'WRIT PETITION'")
    case_number: str = Field(..., description="Case number, e.g., '1847'")
    year: str = Field(..., description="Year of filing, e.g., '2026'")
    petitioner: str = Field(..., description="Name of the petitioner")
    petitioner_details: Optional[str] = Field(default=None, description="Age, occupation, address of petitioner if provided")
    respondents: List[str] = Field(..., description="List of respondents, e.g., ['State of Maharashtra', 'Mumbai Metropolitan Region Development Authority']")
    respondents_details: Optional[Dict[str, str]] = Field(default_factory=dict, description="Address / representation for each respondent")
    filed_on_behalf_of: str = Field(..., description="Target party filing the affidavit, e.g., 'Respondent No. 2'")
    answering_respondent_number: int = Field(..., description="Number of the answering respondent (e.g., 2)")
    answering_respondent_name: str = Field(..., description="Name of answering respondent")


class DeponentDetails(BaseModel):
    name: str = Field(..., description="Full name of the deponent, e.g., 'Arvind Rajan'")
    designation: Optional[str] = Field(default=None, description="Official designation if representing an organisation")
    organisation: Optional[str] = Field(default=None, description="Organisation name if deponent represents an entity")
    address: str = Field(..., description="Address or official office address of deponent")
    age: Optional[str] = Field(default=None, description="Age in years if individual")
    occupation: Optional[str] = Field(default=None, description="Occupation if individual")
    is_organisation: bool = Field(default=False, description="True if respondent party is an authority or company")
    verification_verb: str = Field(default="solemnly affirm", description="Either 'solemnly affirm' or 'swear'")

    @field_validator("verification_verb")
    @classmethod
    def validate_verb(cls, v: str) -> str:
        clean = v.strip().lower()
        if "swear" in clean:
            return "swear and affirm"
        return "solemnly affirm"


class ReplyPoint(BaseModel):
    point_number: int = Field(..., description="Numbered sequential index of reply point")
    title: str = Field(..., description="Point label or heading from case info, e.g. 'Point 1 — Filing of Affidavit in Reply'")
    content_bullets: List[str] = Field(..., description="Bullet points or averments supplied in the case information")
    move_type: str = Field(
        default="SUBSTANTIVE_ANSWER",
        description="Legal move: IDENTITY_AND_PERUSAL, BLANKET_DENIAL, PRELIMINARY_POSITION, SUBSTANTIVE_ANSWER, DOCUMENT_RELIED_UPON, CLOSING"
    )
    exhibit_reference: Optional[str] = Field(default=None, description="e.g. EXHIBIT-'A' if document is annexed")


class PrayerDetails(BaseModel):
    items: List[str] = Field(..., description="Prayer items to be lettered (a), (b), (c)...")


class AttestationDetails(BaseModel):
    place: str = Field(..., description="Place of jurat/affirmation, e.g., 'Mumbai'")
    date_raw: str = Field(..., description="Raw date string from case info, e.g., '5 September 2026'")
    date_ordinal: str = Field(..., description="Legal ordinal format, e.g., '5th day of September 2026'")


class AdvocateDetails(BaseModel):
    firm_name: str = Field(..., description="Advocate firm or name, e.g., 'Rajan & Associates'")
    acting_for: str = Field(..., description="Party represented, e.g., 'Respondent No. 2'")


class CaseInformationSchema(BaseModel):
    """
    Structured Intermediate Representation (IR) holding all extracted facts
    prior to drafting the Affidavit.
    """
    case_details: CourtAndCaseDetails
    deponent: DeponentDetails
    reply_points: List[ReplyPoint]
    prayer: PrayerDetails
    attestation: AttestationDetails
    advocate: AdvocateDetails
    source_evidence: Dict[str, str] = Field(default_factory=dict, description="Traceability map from entity to source case text")

    @model_validator(mode="after")
    def validate_rules(self) -> "CaseInformationSchema":
        # Rule 1: Organisation Deponent Rule check
        if self.deponent.organisation or "authority" in self.case_details.answering_respondent_name.lower() or "limited" in self.case_details.answering_respondent_name.lower():
            self.deponent.is_organisation = True
            if not self.deponent.designation:
                raise ValueError("An organisation deponent MUST have a valid designation (cannot say 'I am the Respondent' directly).")
        
        # Rule 2: Answering respondent consistency
        if f"Respondent No. {self.case_details.answering_respondent_number}" not in self.case_details.filed_on_behalf_of:
            raise ValueError(f"filed_on_behalf_of '{self.case_details.filed_on_behalf_of}' does not match answering_respondent_number {self.case_details.answering_respondent_number}")
        
        return self


# --- Evaluation Schemas ---

class DeterministicCheckResult(BaseModel):
    rule_id: str
    name: str
    passed: bool
    expected: str
    actual: str
    details: str


class DimensionScore(BaseModel):
    dimension_name: str
    score: float = Field(..., ge=0, le=100)
    weight: float = Field(..., ge=0, le=1.0)
    issues_detected: List[str] = Field(default_factory=list)
    explanation: str


class EvaluationReportSchema(BaseModel):
    overall_score: float = Field(..., ge=0, le=100)
    dimension_scores: Dict[str, DimensionScore]
    deterministic_checks: List[DeterministicCheckResult]
    detected_issues: List[Dict[str, Any]]
    score_calculation_explanation: str
    document_summary: str
    passed_all_deterministic: bool
