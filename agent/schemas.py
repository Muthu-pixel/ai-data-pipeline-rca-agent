from enum import Enum

from pydantic import BaseModel, Field, model_validator


# Categories are uncommented one at a time as each gets a real fixture behind
# it (see sample-pipeline). schema_drift and data_quality are live; the rest
# are added as sample-pipeline grows new real scenarios for them. OTHER is a
# permanent catch-all, not part of that rollout: it's how a failure that
# doesn't fit any live category gets surfaced honestly instead of forced into
# the closest wrong one. Review OTHER-classified reports periodically -- a
# recurring pattern there is the real-world signal that a new category is
# ready to be added (with its own sample-pipeline fixture) and uncommented.
class FailureCategory(str, Enum):
    SCHEMA_DRIFT = "schema_drift"
    DATA_QUALITY = "data_quality"
    #CODE_BUG = "code_bug"
    #INFRA_TIMEOUT = "infra_timeout"
    #CREDENTIAL_CONFIG = "credential_config"
    #RESOURCE_EXHAUSTION = "resource_exhaustion"
    OTHER = "other"


class EvidenceCitation(BaseModel):
    source: str = Field(description="Where this evidence came from, e.g. a log file path or tool name.")
    quote: str = Field(description="The exact excerpt (log line, field name, metric value) that supports the claim.")
    relevance: str = Field(description="Why this excerpt supports the root-cause claim.")


class ImpactAnalysis(BaseModel):
    affected_component: str = Field(description="The pipeline stage or system component that failed.")
    severity: str = Field(description="How serious the failure is, e.g. 'run blocked' vs 'degraded output'.")
    downstream_effects: str = Field(description="What breaks or is at risk downstream as a result.")


class RemediationSuggestion(BaseModel):
    summary: str = Field(description="One-line description of the suggested fix.")
    steps: list[str] = Field(description="Concrete, ordered steps an SRE would take to apply the fix.")
    risk_notes: str = Field(description="Caveats or risks of applying this fix, if any.")


class RCAReport(BaseModel):
    category: FailureCategory = Field(description="The classified root cause of the pipeline failure.")
    confidence: float = Field(ge=0.0, le=1.0, description="Calibrated confidence in this classification, 0-1.")
    needs_more_context: bool = Field(
        description="True if the available evidence was insufficient to confidently classify the failure."
    )
    summary: str = Field(description="A concise, human-readable summary of what went wrong.")
    evidence: list[EvidenceCitation] = Field(description="Evidence citations backing the classification.")
    impact: ImpactAnalysis
    remediation: RemediationSuggestion

    @model_validator(mode="after")
    def other_requires_more_context(self) -> "RCAReport":
        if self.category == FailureCategory.OTHER and not self.needs_more_context:
            raise ValueError("category='other' must have needs_more_context=True -- it's a catch-all, not a confident classification")
        return self
