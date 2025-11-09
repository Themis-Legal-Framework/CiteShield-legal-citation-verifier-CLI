"""Structured outputs produced by the citation agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


VerificationStatus = Literal["verified", "needs_review", "not_found", "contradicted"]
CitationType = Literal["case", "statute", "regulation", "secondary", "unknown"]
RiskLevel = Literal["low", "medium", "high"]


class CitationAssessment(BaseModel):
    """Represents the agent's verdict for a single citation."""

    citation_text: str = Field(..., description="Citation exactly as it appears in the filing.")
    citation_type: CitationType = Field(..., description="What kind of authority this citation is.")
    proposition_summary: str = Field(
        ..., description="The legal rule or fact the brief attributes to this citation."
    )
    verification_status: VerificationStatus = Field(
        ...,
        description=(
            "'verified' if the cited authority supports the proposition, 'needs_review' if more"
            " checking is required, 'not_found' if the case/statute could not be located, or"
            " 'contradicted' if the authority says the opposite."
        ),
    )
    reasoning: str = Field(..., description="Why the status above was selected.")
    supporting_authorities: list[str] = Field(
        default_factory=list,
        description="Specific quotes, docket numbers, reporter cites, or URLs confirming the result.",
    )
    risk_level: RiskLevel = Field(
        ...,
        description="How urgent this citation is to fix before filing.",
    )
    recommended_fix: str | None = Field(
        default=None,
        description="Optional suggestion such as replacing the citation or softening the language.",
    )


class CitationVerificationReport(BaseModel):
    """Final response returned by the CLI once the agent finishes reasoning."""

    document_name: str = Field(..., description="Name of the uploaded brief or memo.")
    overall_assessment: Literal["pass", "needs_review", "high_risk"] = Field(
        ...,
        description="Aggregate risk score for the whole brief.",
    )
    total_citations: int = Field(..., description="How many citations were extracted.")
    verified_citations: int = Field(..., description="Count of citations marked as verified.")
    flagged_citations: int = Field(..., description="Citations labeled needs_review or contradicted.")
    unable_to_locate: int = Field(..., description="Citations marked as not_found.")
    narrative_summary: str = Field(..., description="Short human-readable recap.")
    citations: list[CitationAssessment] = Field(
        default_factory=list,
        description="Per-citation analysis objects.",
    )
