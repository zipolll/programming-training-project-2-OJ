"""Strict models for AI-assisted problem authoring."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.modules.problems.models import Problem


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


def validate_provider_url(value: str, allow_local_http: bool = True) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise ValueError("provider URL must not include credentials")
    if not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("invalid provider URL")
    hostname = parsed.hostname.lower().rstrip(".")
    blocked = {"169.254.169.254", "metadata.google.internal"}
    if hostname in blocked or hostname.startswith("169.254."):
        raise ValueError("provider URL targets a blocked metadata address")
    local = hostname in {"localhost", "127.0.0.1", "::1"}
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_link_local) and not local:
        raise ValueError("provider URL targets a private or link-local address")
    if parsed.scheme != "https" and not (allow_local_http and parsed.scheme == "http" and local):
        raise ValueError("provider URL must use HTTPS (HTTP is allowed only for localhost)")
    return value.rstrip("/")


class AgentConfigUpdate(StrictModel):
    provider_url: str = Field(min_length=1, max_length=2048)
    model_name: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    input_price_per_million_tokens: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    output_price_per_million_tokens: Decimal = Field(default=Decimal("0"), ge=0, strict=False)
    currency: str = Field(default="USD", min_length=1, max_length=12)
    request_timeout: float = Field(default=360.0, gt=0, le=600, allow_inf_nan=False)
    max_iterations: int = Field(default=3, ge=1, le=10)
    max_output_tokens: int = Field(default=50000, ge=256, le=128000)

    @field_validator("provider_url")
    @classmethod
    def url_is_safe(cls, value: str) -> str:
        return validate_provider_url(value)


class AgentConfigView(StrictModel):
    provider_url: str
    model_name: str
    masked_api_key: str
    has_api_key: bool
    encryption_configured: bool
    input_price_per_million_tokens: Decimal
    output_price_per_million_tokens: Decimal
    currency: str
    request_timeout: float
    max_iterations: int
    max_output_tokens: int


class AuthoringRequest(StrictModel):
    required_knowledge: list[str] = Field(min_length=1, max_length=30)
    difficulty: str = Field(min_length=1, max_length=50)
    problem_type: str = Field(min_length=1, max_length=100)
    expected_algorithm: str = Field(default="", max_length=500)
    forbidden_knowledge: list[str] = Field(default_factory=list, max_length=30)
    data_scale: str = Field(default="", max_length=500)
    time_limit: float = Field(default=2.0, gt=0, le=60, allow_inf_nan=False)
    memory_limit: int = Field(default=128, ge=16, le=4096)
    background_preference: str = Field(default="", max_length=2000)
    testcase_count: int = Field(default=10, ge=1, le=100)
    additional_requirements: str = Field(default="", max_length=10000)
    adapt_existing: bool = False
    existing_problem_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def existing_problem_is_consistent(self) -> "AuthoringRequest":
        if self.adapt_existing and not self.existing_problem_id:
            raise ValueError("existing_problem_id is required when adapting a problem")
        if not any(item.strip() for item in self.required_knowledge):
            raise ValueError("authoring requirements must not be empty")
        return self


class RefineRequest(StrictModel):
    feedback: str = Field(min_length=1, max_length=10000)


class GeneratedProblem(StrictModel):
    problem: Problem
    solution_explanation: str = Field(min_length=1)
    complexity_analysis: str = Field(min_length=1)
    reference_solution_language: str = Field(default="python", pattern=r"^(python|cpp)$")
    reference_solution: str = Field(min_length=1, max_length=1_000_000)
    wrong_solutions: list[str] = Field(default_factory=list, max_length=5)


class ValidationReport(StrictModel):
    schema_valid: bool = False
    reference_all_passed: bool = False
    samples_consistent: bool = False
    testcase_count: int = 0
    boundary_coverage: list[str] = Field(default_factory=list)
    random_or_combinatorial_coverage: bool = False
    maximum_data_scale: str = "unknown"
    distinguishes_bruteforce: bool = False
    wrong_solutions_run: int = 0
    wrong_solution_detections: dict[str, list[int]] = Field(default_factory=dict)
    blocking_errors: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    tool_evidence: list[dict[str, Any]] = Field(default_factory=list)


class AgentTask(StrictModel):
    task_id: str
    user_id: int
    parent_task_id: str | None = None
    revision: int
    status: AgentStatus
    stage: str
    progress: int = Field(ge=0, le=100)
    request: AuthoringRequest
    draft: GeneratedProblem | None = None
    final_problem: GeneratedProblem | None = None
    validation_report: ValidationReport | None = None
    error_code: str | None = None
    safe_error_message: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: Decimal = Decimal("0")
    currency: str = "USD"
    usage_estimated: bool = False
    cancellation_requested: bool = False
    created_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    finished_at: datetime | None = None


class AgentEvent(StrictModel):
    event_id: int
    task_id: str
    stage: str
    event_type: str
    message: str
    progress: int
    timestamp: datetime


class ImportRequest(StrictModel):
    confirm: bool = False
    update_existing: bool = False
