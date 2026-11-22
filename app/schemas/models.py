from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class InboundLead(BaseModel):
    sender_name: str
    sender_email: str
    company_name: str
    subject: str
    email_body: str

class ExtractedLeadData(BaseModel):
    company_name: str = Field(description="Name of the prospect's company")
    company_domain: str = Field(description="Website domain inferred from email or body, e.g., acme.com")
    industry: str = Field(description="Industry sector, e.g., Fintech, Healthcare, E-commerce, Other")
    estimated_budget_usd: int = Field(description="Monthly or annual budget mentioned in USD. Put 0 if not mentioned.")
    required_compliance: List[str] = Field(default_factory=list, description="Compliance needs like SOC2, HIPAA, GDPR")
    key_pain_points: List[str] = Field(description="List of specific technical or business problems mentioned")
    urgency_score: int = Field(ge=1, le=10, description="1 to 10 score of buying intent and urgency")
    is_qualified: bool = Field(description="False if spam, job seeker, or clearly below $1,500/mo budget")
    disqualification_reason: Optional[str] = Field(default=None, description="Reason if is_qualified is False")

class ProposalDraft(BaseModel):
    recommended_tier: str = Field(description="Must be one of: Starter Tier, Growth Tier, Enterprise Tier")
    quoted_monthly_price_usd: int = Field(description="Monthly price in USD matching our pricing rules")
    email_subject: str = Field(description="Compelling subject line for the reply email")
    proposal_markdown: str = Field(description="Full, tailored technical proposal and email response in Markdown")
    crm_deal_stage: str = Field(description="e.g., Discovery Scheduled, Proposal Sent, Disqualified")
    citations_used: List[str] = Field(description="Names of internal documents referenced")

    @field_validator("recommended_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        allowed = ["Starter Tier", "Growth Tier", "Enterprise Tier"]
        if v not in allowed:
            raise ValueError(f"Tier must be one of {allowed}, got {v}")
        return v

    @field_validator("quoted_monthly_price_usd")
    @classmethod
    def validate_minimum_price(cls, v: int) -> int:
        if v < 1500:
            raise ValueError("Minimum allowable monthly quote is $1,500.")
        return v