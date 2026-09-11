"""Calibration: observer scores against hand scores (spec §6)."""
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .constructs import CONSTRUCTS

TARGET_AGREEMENT = 0.8
DISAGREE_AT = 2


def load_human_scores(path: Path) -> dict[str, dict[str, dict[str, int]]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {sid: {rater: {c: int(v) for c, v in (scores or {}).items()} for rater, scores in (raters or {}).items()}
            for sid, raters in (data.get("sessions") or {}).items()}


def median_scores(raters: dict[str, dict[str, int]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in CONSTRUCTS:
        vals = [r[c] for r in raters.values() if c in r]
        if vals:
            out[c] = statistics.median(vals)
    return out


@dataclass
class Disagreement:
    session_id: str
    construct: str
    observer: int
    human_median: float
    delta: float


@dataclass
class Report:
    n_scores: int = 0
    n_within_1: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def agreement(self) -> float:
        return self.n_within_1 / self.n_scores if self.n_scores else 0.0

    @property
    def passed(self) -> bool:
        return self.n_scores > 0 and self.agreement >= TARGET_AGREEMENT


def agreement(observer: dict[str, dict], human: dict[str, dict[str, dict[str, int]]]) -> Report:
    rep = Report()
    for sid in sorted(set(observer) | set(human)):
        if sid not in observer or sid not in human:
            rep.missing.append(sid)
            continue
        for c, m in median_scores(human[sid]).items():
            o = int(observer[sid]["constructs"][c]["score"])
            rep.n_scores += 1
            d = abs(o - m)
            if d <= 1:
                rep.n_within_1 += 1
            if d >= DISAGREE_AT:
                rep.disagreements.append(Disagreement(sid, c, o, m, float(d)))
    return rep


def render(rep: Report) -> str:
    lines = [f"agreement: {rep.n_within_1}/{rep.n_scores} within 1 point = {rep.agreement:.0%}  "
             f"(target {TARGET_AGREEMENT:.0%}) → {'PASS' if rep.passed else 'FAIL'}"]
    if rep.disagreements:
        lines.append(f"\n≥{DISAGREE_AT}-point disagreements — tighten these anchors in ember/bank/rubric.yaml:")
        for c in CONSTRUCTS:
            for d in (x for x in rep.disagreements if x.construct == c):
                lines.append(f"  {c}  {d.session_id}  observer {d.observer}  human median {d.human_median:g}  Δ{d.delta:g}")
    if rep.missing:
        lines.append("\nno observer/human pair for: " + ", ".join(rep.missing))
    return "\n".join(lines)
