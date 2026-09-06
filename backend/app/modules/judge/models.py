"""Validated models shared by language management and the judge engine."""

import re
import shlex
from enum import Enum
from pathlib import Path
from string import Formatter

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LANGUAGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_+-]{0,31}$")
FILE_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9]{1,10}$")
ALLOWED_PLACEHOLDERS = frozenset({"src", "exe"})
SHELL_METACHARACTERS = frozenset(";&|<>`$\n\r\x00")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TestcaseStatus(str, Enum):
    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    CE = "CE"
    UNK = "UNK"


class JudgeRequest(StrictModel):
    problem_id: str = Field(min_length=1, max_length=64)
    language: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=1, max_length=1_000_000)


class TestcaseResult(StrictModel):
    id: int = Field(ge=1)
    result: TestcaseStatus
    time: float = Field(ge=0)
    memory: float = Field(ge=0)
    error_summary: str = ""


class JudgeResult(StrictModel):
    status: TestcaseStatus
    score: int = Field(ge=0)
    compile_info: str | None = None
    stdout: str = ""
    stderr: str = ""
    time: float = Field(ge=0)
    memory: float = Field(ge=0)
    testcase_results: list[TestcaseResult] = Field(default_factory=list)


class LanguageConfig(StrictModel):
    name: str
    file_ext: str
    compile_args: tuple[str, ...] | None = None
    run_args: tuple[str, ...]
    time_limit: float = Field(gt=0, le=60, allow_inf_nan=False)
    memory_limit: int = Field(gt=0, le=4096)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not LANGUAGE_NAME_PATTERN.fullmatch(value):
            raise ValueError("invalid language name")
        return value

    @field_validator("file_ext")
    @classmethod
    def validate_file_ext(cls, value: str) -> str:
        if not FILE_EXTENSION_PATTERN.fullmatch(value):
            raise ValueError("invalid source file extension")
        return value

    @model_validator(mode="after")
    def validate_templates(self) -> "LanguageConfig":
        compile_fields = command_placeholders(self.compile_args or ())
        run_fields = command_placeholders(self.run_args)
        if not self.run_args:
            raise ValueError("run command is required")
        if self.compile_args is not None:
            if not {"src", "exe"}.issubset(compile_fields) or "exe" not in run_fields:
                raise ValueError("compiled languages require {src} and {exe}")
        elif "src" not in run_fields:
            raise ValueError("interpreted languages require {src}")
        return self

    def expand_compile(self, source: Path, executable: Path) -> list[str] | None:
        if self.compile_args is None:
            return None
        return expand_command(self.compile_args, source, executable)

    def expand_run(self, source: Path, executable: Path) -> list[str]:
        return expand_command(self.run_args, source, executable)


class LanguageRegistration(StrictModel):
    name: str
    file_ext: str
    compile_cmd: str | None = Field(default=None, max_length=1024)
    run_cmd: str = Field(min_length=1, max_length=1024)
    time_limit: float = Field(default=3.0, gt=0, le=60, allow_inf_nan=False)
    memory_limit: int = Field(default=128, gt=0, le=4096)

    def to_config(self) -> LanguageConfig:
        return LanguageConfig(
            name=self.name,
            file_ext=self.file_ext,
            compile_args=parse_command(self.compile_cmd) if self.compile_cmd else None,
            run_args=parse_command(self.run_cmd),
            time_limit=self.time_limit,
            memory_limit=self.memory_limit,
        )


def parse_command(command: str) -> tuple[str, ...]:
    """Parse a command template without invoking a shell."""
    if any(character in command for character in SHELL_METACHARACTERS):
        raise ValueError("shell operators are not allowed")
    try:
        arguments = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise ValueError("invalid command template") from exc
    if not arguments or any(not argument for argument in arguments):
        raise ValueError("command must contain an executable")
    command_placeholders(arguments)
    return arguments


def command_placeholders(arguments: tuple[str, ...]) -> set[str]:
    fields: set[str] = set()
    try:
        for argument in arguments:
            for _, field_name, format_spec, conversion in Formatter().parse(argument):
                if field_name is None:
                    continue
                if field_name not in ALLOWED_PLACEHOLDERS or format_spec or conversion:
                    raise ValueError("unsupported command placeholder")
                fields.add(field_name)
    except ValueError as exc:
        raise ValueError("invalid command placeholder") from exc
    return fields


def expand_command(arguments: tuple[str, ...], source: Path, executable: Path) -> list[str]:
    values = {"src": str(source), "exe": str(executable)}
    return [argument.format_map(values) for argument in arguments]
