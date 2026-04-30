"""Pydantic schemas for FastAPI request/response bodies."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ApplyStatus = Literal["applied", "failed", "needs_manual", "skipped"]
PipelineStage = Literal[
    "discovered",
    "pending_detail",
    "enriched",
    "pending_score",
    "scored",
    "pending_tailor",
    "tailored",
    "pending_apply",
    "applied",
]


class Job(BaseModel):
    """One row from the ``jobs`` table. All fields optional because the
    table has 29 columns, populated incrementally across pipeline stages."""

    url: str
    title: str | None = None
    site: str | None = None
    location: str | None = None
    salary: str | None = None
    description: str | None = None
    full_description: str | None = None
    fit_score: int | None = None
    score_reasoning: str | None = None
    application_url: str | None = None
    tailored_resume_path: str | None = None
    cover_letter_path: str | None = None
    apply_status: str | None = None
    apply_error: str | None = None
    discovered_at: str | None = None
    detail_scraped_at: str | None = None
    scored_at: str | None = None
    tailored_at: str | None = None
    cover_letter_at: str | None = None
    applied_at: str | None = None
    last_attempted_at: str | None = None
    tailor_attempts: int | None = None
    cover_attempts: int | None = None
    apply_attempts: int | None = None

    model_config = {"extra": "allow"}


class ApplicationUrlUpdate(BaseModel):
    application_url: str | None


class TailoredResumeUpdate(BaseModel):
    path: str


class NeedsManualUpdate(BaseModel):
    error: str


class DeleteResult(BaseModel):
    deleted: int


class UpdateResult(BaseModel):
    updated: bool


class StatsResponse(BaseModel):
    total: int
    pending_detail: int
    with_description: int
    detail_errors: int
    scored: int
    unscored: int
    score_distribution: list[tuple[int, int]] = Field(default_factory=list)
    tailored: int
    untailored_eligible: int
    tailor_exhausted: int
    with_cover_letter: int
    cover_exhausted: int
    applied: int
    apply_errors: int
    ready_to_apply: int
    by_site: list[tuple[str, int]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class PipelineRunResponse(BaseModel):
    """Standard 202 response for long-running pipeline triggers."""

    accepted: bool = True
    stage: str
    detail: str | None = None
