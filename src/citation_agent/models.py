"""Structured outputs produced by the citation agent.

This module defines the Pydantic models that structure the output of the CiteShield
citation verification agent. These models enforce strict schemas for the agent's
responses, ensuring consistent and machine-readable results.

The main models are:
    - CitationAssessment: Individual citation analysis
    - CitationVerificationReport: Complete report for an entire document

Type Definitions:
    VerificationStatus: Status of citation verification (verified, needs_review, not_found, contradicted)
    CitationType: Category of legal authority (case, statute, regulation, secondary, unknown)
    RiskLevel: Risk assessment (low, medium, high)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


VerificationStatus = Literal["verified", "needs_review", "not_found", "contradicted"]
"""Verification status for a citation.

- 'verified': Citation found and supports the stated proposition
- 'needs_review': Requires additional human review
- 'not_found': Citation could not be located
- 'contradicted': Citation says the opposite of what's claimed
"""

CitationType = Literal["case", "statute", "regulation", "secondary", "unknown"]
"""Type of legal authority being cited.

- 'case': Court decision/opinion
- 'statute': Legislative law
- 'regulation': Administrative rule
- 'secondary': Law review, treatise, etc.
- 'unknown': Cannot determine type
"""

RiskLevel = Literal["low", "medium", "high"]
"""Risk level for filing with this citation.

- 'low': Safe to file, citation verified
- 'medium': Should review before filing
- 'high': Critical issue, must fix before filing
"""


class CitationAssessment(BaseModel):
    """Represents the agent's verdict for a single citation.

    This model captures the complete analysis of one legal citation found in a
    document, including what was claimed, whether it's accurate, and recommendations.

    Attributes:
        citation_text: The exact citation string from the document
        citation_type: Category of legal authority (case, statute, etc.)
        proposition_summary: What the document claims this citation supports
        verification_status: Whether the citation was verified
        reasoning: Explanation of why this status was assigned
        supporting_authorities: Evidence used to verify (URLs, quotes, etc.)
        risk_level: How urgent it is to address this citation
        recommended_fix: Optional suggestion for correcting the citation
    """

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
    """Final response returned by the CLI once the agent finishes reasoning.

    This is the top-level report generated after analyzing an entire legal document.
    It contains aggregate statistics and a list of individual citation assessments.

    Attributes:
        document_name: Name of the analyzed file
        overall_assessment: Aggregate risk level ('pass', 'needs_review', or 'high_risk')
        total_citations: Total number of citations found in the document
        verified_citations: Count of citations successfully verified
        flagged_citations: Citations requiring attention (needs_review or contradicted)
        unable_to_locate: Citations that could not be found
        narrative_summary: Human-readable summary of the analysis
        citations: Detailed breakdown of each individual citation
    """

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
