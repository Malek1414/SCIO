"""Question bank: schema, validation rules (spec §5.1, §5.2), loader."""
from pathlib import Path
from typing import Iterable

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .constructs import CONSTRUCTS, CLUSTER_OF, TAGS, FRAMINGS

BANK_DIR = Path(__file__).parent / "bank"

YES_NO_STARTS = ("do ", "does ", "did ", "are ", "is ", "was ", "were ", "have ", "has ", "had ",
                 "can ", "could ", "will ", "would ", "should ")


def _open_question(text: str) -> str:
    if text.strip().lower().startswith(YES_NO_STARTS):
        raise ValueError(f"yes/no question not allowed: {text[:50]!r}")
    return text


class Candidate(BaseModel):
    id: str
    slot: int = Field(ge=2, le=6)
    cluster: str
    targets: list[str] = Field(min_length=1)
    threat: int = Field(ge=1, le=7)
    framing: str
    prerequisites: list[str] = Field(default_factory=list)
    default: bool = False
    text: str
    rephrase: str

    @field_validator("targets")
    @classmethod
    def _targets_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in CONSTRUCTS]
        if bad:
            raise ValueError(f"unknown construct(s) {bad}")
        return v

    @field_validator("prerequisites")
    @classmethod
    def _tags_known(cls, v: list[str]) -> list[str]:
        bad = [t for t in v if t not in TAGS]
        if bad:
            raise ValueError(f"unknown tag(s) {bad}")
        return v

    @field_validator("framing")
    @classmethod
    def _framing_known(cls, v: str) -> str:
        if v not in FRAMINGS:
            raise ValueError(f"unknown framing {v!r}")
        return v

    @field_validator("text", "rephrase")
    @classmethod
    def _open(cls, v: str) -> str:
        return _open_question(v)

    @model_validator(mode="after")
    def _consistency(self) -> "Candidate":
        for t in self.targets:
            if CLUSTER_OF[t] != self.cluster:
                raise ValueError(f"{self.id}: target {t} is not in cluster {self.cluster}")
        if self.slot == 2 and self.prerequisites:
            raise ValueError(f"{self.id}: slot 2 candidates must have no prerequisites")
        return self


class Opener(BaseModel):
    text: str
    rephrase: str
    fallback_take_home: str

    @field_validator("text", "rephrase")
    @classmethod
    def _open(cls, v: str) -> str:
        return _open_question(v)

    @field_validator("fallback_take_home")
    @classmethod
    def _is_question(cls, v: str) -> str:
        if not v.strip().endswith("?"):
            raise ValueError("fallback_take_home must end with '?'")
        return v


class Anchor(BaseModel):
    score: int
    description: str
    exemplar: str

    @field_validator("score")
    @classmethod
    def _147(cls, v: int) -> int:
        if v not in (1, 4, 7):
            raise ValueError("anchor score must be 1, 4 or 7")
        return v


class RubricEntry(BaseModel):
    construct: str
    name: str
    inverse: bool = False
    anchors: list[Anchor] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _scores_complete(self) -> "RubricEntry":
        if {a.score for a in self.anchors} != {1, 4, 7}:
            raise ValueError(f"{self.construct}: anchors must be exactly scores 1, 4, 7")
        return self


class Bank(BaseModel):
    opener: Opener
    candidates: list[Candidate]
    rubric: dict[str, RubricEntry]

    @model_validator(mode="after")
    def _structure(self) -> "Bank":
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate ids")
        for slot in range(2, 7):
            cs = [c for c in self.candidates if c.slot == slot]
            if len(cs) < 3:
                raise ValueError(f"slot {slot} needs at least 3 candidates, has {len(cs)}")
            if sum(c.default for c in cs) != 1:
                raise ValueError(f"slot {slot} must have exactly one default candidate")
        if set(self.rubric) != set(CONSTRUCTS):
            raise ValueError(f"rubric must cover exactly {CONSTRUCTS}")
        return self

    def for_slot(self, slot: int, used: Iterable[str] = frozenset()) -> list[Candidate]:
        used = set(used)
        if slot == 7:
            return [c for c in self.candidates if c.slot in (5, 6) and c.id not in used]
        return [c for c in self.candidates if c.slot == slot]

    def default_for(self, slot: int, used: Iterable[str] = frozenset()) -> "Candidate | None":
        used = set(used)
        if slot == 7:
            pool = self.for_slot(7, used)
            for c in pool:                      # prefer an unused default, slot 5 first
                if c.default:
                    return c
            return pool[0] if pool else None
        return next(c for c in self.candidates if c.slot == slot and c.default)

    def by_id(self, cid: str) -> Candidate:
        return next(c for c in self.candidates if c.id == cid)


def load_bank(dir: Path = BANK_DIR) -> Bank:
    opener = yaml.safe_load((dir / "opener.yaml").read_text(encoding="utf-8"))
    qs = yaml.safe_load((dir / "questions.yaml").read_text(encoding="utf-8"))
    rub = yaml.safe_load((dir / "rubric.yaml").read_text(encoding="utf-8"))
    return Bank(opener=opener, candidates=qs["candidates"], rubric={r["construct"]: r for r in rub["rubric"]})
