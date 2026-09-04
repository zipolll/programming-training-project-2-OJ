"""Validated problem configuration models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonEmptyText = Annotated[str, Field(strict=True, min_length=1)]
ProblemId = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Sample(_StrictModel):
    """One public sample input/output pair."""

    input: str = Field(strict=True)
    output: str = Field(strict=True)


class Testcase(_StrictModel):
    """One private judging input/output pair."""

    input: str = Field(strict=True)
    output: str = Field(strict=True)


class Problem(_StrictModel):
    """Complete on-disk and API representation of an OJ problem."""

    id: ProblemId
    title: NonEmptyText
    description: NonEmptyText
    input_description: NonEmptyText
    output_description: NonEmptyText
    samples: list[Sample] = Field(min_length=1)
    constraints: NonEmptyText
    testcases: list[Testcase] = Field(min_length=1)
    hint: str = Field(default="", strict=True)
    source: str = Field(default="", strict=True)
    tags: list[NonEmptyText] = Field(default_factory=list)
    time_limit: float = Field(default=3.0, strict=True, gt=0, allow_inf_nan=False)
    memory_limit: int = Field(default=128, strict=True, gt=0)
    author: str = Field(default="", strict=True)
    difficulty: str = Field(default="", strict=True)
    problem_type: str = Field(default="", strict=True, max_length=100)


class ProblemSummary(_StrictModel):
    """Fields exposed by the problem list endpoint."""

    id: ProblemId
    title: NonEmptyText
    difficulty: str
    problem_type: str
    tags: list[NonEmptyText]
    source: str
    author: str
