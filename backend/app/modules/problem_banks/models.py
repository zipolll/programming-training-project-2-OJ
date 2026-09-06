"""Validated collection requests."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.modules.problems.repository import validate_problem_id


class BankInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=200)


class ProblemIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_ids: list[str] = Field(min_length=1)

    @field_validator("problem_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_problem_id(value)
        return list(dict.fromkeys(values))


class MoveInput(ProblemIds):
    target_bank_id: int = Field(gt=0)


class CreateBankInput(BankInput, ProblemIds):
    problem_ids: list[str] = Field(default_factory=list)
