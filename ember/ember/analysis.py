"""Cohort typing over observer scores (spec 2026-09-16-cohort-typing-design §4.1).

Pure functions. No file access, no network, no LLM. Deterministic: every tie is broken
by subject code, so the same cohort always produces byte-identical output.
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass

from .constructs import CONSTRUCTS

FLAT_SD = 0.5          # within-person sd at or below this: no shape to cluster on
FLOOR_MAX = 4          # cohort max at or below this: the construct floors
CEILING_MIN = 5        # "scored high" threshold, used for the ≥5 counts
FLOOR_MEAN = 1.5       # mean at or below this: floor across the board, no engagement signal
PILOT_CODES = ("TEST", "S00")   # operator dry-runs, never study subjects


def zprofile(scores: dict[str, int]) -> list[float]:
    """Within-person z-score, in CONSTRUCTS order. Isolates shape from overall level."""
    v = [float(scores[c]) for c in CONSTRUCTS]
    m = st.mean(v)
    sd = st.pstdev(v)
    if sd == 0:
        return [0.0] * len(v)
    return [(x - m) / sd for x in v]


def shape_distance(a: list[float], b: list[float]) -> float:
    """Correlation distance, 1 - r, in [0, 2]. A flat vector has no shape: distance 1.0."""
    ma, mb = st.mean(a), st.mean(b)
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    if da == 0 or db == 0:
        return 1.0
    r = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (da * db)
    return 1.0 - r


@dataclass(frozen=True)
class Merge:
    height: float
    left: tuple[str, ...]
    right: tuple[str, ...]

    @property
    def members(self) -> tuple[str, ...]:
        return self.left + self.right


def linkage(profiles: dict[str, list[float]]) -> list[Merge]:
    """Average-linkage agglomerative clustering on shape distance.

    Ties break by the lexically smallest member, so the result never depends on
    dict insertion order.
    """
    clusters: list[tuple[str, ...]] = [(c,) for c in sorted(profiles)]
    merges: list[Merge] = []
    while len(clusters) > 1:
        best = None
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                d = st.mean([shape_distance(profiles[a], profiles[b])
                             for a in clusters[i] for b in clusters[j]])
                key = (round(d, 12), min(clusters[i]), min(clusters[j]))
                if best is None or key < best[0]:
                    best = (key, d, i, j)
        _, d, i, j = best
        left, right = clusters[i], clusters[j]
        merges.append(Merge(height=d, left=left, right=right))
        clusters = [c for k, c in enumerate(clusters) if k not in (i, j)] + [left + right]
    return merges


def seriate(merges: list[Merge]) -> list[str]:
    """Row order for the heat signature: the final merge's members, in merge order."""
    return list(merges[-1].members) if merges else []


def cut(merges: list[Merge], k: int) -> list[tuple[str, ...]]:
    """The k groups that exist after applying all but the last k-1 merges."""
    n = len(merges) + 1
    if not 1 <= k <= n:
        raise ValueError(f"k must be in 1..{n}, got {k}")
    clusters: list[tuple[str, ...]] = [(c,) for c in sorted(seriate(merges))]
    for m in merges[: n - k]:
        clusters = [c for c in clusters if c not in (m.left, m.right)] + [m.members]
    return sorted((tuple(sorted(c)) for c in clusters), key=lambda g: g[0])


def score_of(subject: dict, cid: str) -> int | None:
    """Read one construct score, or None when the subject has no entry for it.

    data.js nests the score under "score"; older shapes store a bare int. Contributed
    results are not guaranteed to carry all nine constructs, so callers must handle None.
    """
    v = (subject.get("scores") or {}).get(cid)
    if v is None:
        return None
    return int(v["score"]) if isinstance(v, dict) else int(v)


def engagement_outliers(subjects: list[dict]) -> dict[str, str]:
    """Subjects with no usable shape. A flat profile clusters arbitrarily, so it must not be typed.

    A subject missing any construct is also excluded: shape is only meaningful across all nine.
    """
    out: dict[str, str] = {}
    for s in sorted(subjects, key=lambda x: x["subject_code"]):
        v = [score_of(s, c) for c in CONSTRUCTS]
        if any(x is None for x in v):
            missing = [c for c in CONSTRUCTS if score_of(s, c) is None]
            out[s["subject_code"]] = f"incomplete scores (missing {', '.join(missing)})"
            continue
        sd, mean = st.pstdev(v), st.mean(v)
        if sd <= FLAT_SD:
            out[s["subject_code"]] = (f"flat profile (sd {sd:.2f} ≤ {FLAT_SD}, mean {mean:.1f}) "
                                      f"— no shape to type on")
        elif mean <= FLOOR_MEAN:
            out[s["subject_code"]] = (f"at floor across the board (mean {mean:.2f} ≤ {FLOOR_MEAN}) "
                                      f"— non-engagement, not a profile")
    return out


def constants_and_discriminators(subjects: list[dict]) -> dict:
    """Split the nine constructs into those that describe the cohort and those that separate it.

    A construct is a *constant* when the cohort never spreads across it — either it floors
    (max ≤ FLOOR_MAX) or everyone scores high (min ≥ CEILING_MIN). A construct nobody was
    scored on distinguishes nobody either, so it counts as a constant with n=0.
    """
    stats: dict[str, dict] = {}
    constants: list[str] = []
    discriminators: list[str] = []
    for c in CONSTRUCTS:
        v = [x for x in (score_of(s, c) for s in subjects) if x is not None]
        if not v:
            stats[c] = {"mean": None, "min": None, "max": None, "sd": None, "n": 0, "n_high": 0}
            constants.append(c)
            continue
        row = {"mean": round(st.mean(v), 2), "min": min(v), "max": max(v),
               "sd": round(st.pstdev(v), 2), "n": len(v),
               "n_high": sum(1 for x in v if x >= CEILING_MIN)}
        stats[c] = row
        (constants if (row["max"] <= FLOOR_MAX or row["min"] >= CEILING_MIN)
         else discriminators).append(c)
    return {"constants": constants, "discriminators": discriminators, "stats": stats}


DEFAULT_K = 4


def bank_coverage(bank) -> dict[str, int]:
    """How many candidate questions target each construct. Drives the caveat annotations."""
    counts = {c: 0 for c in CONSTRUCTS}
    for q in bank.candidates:
        for t in q.targets:
            if t in counts:
                counts[t] += 1
    return counts


def analyse(subjects: list[dict], bank, *, k: int = DEFAULT_K,
            pilots: tuple[str, ...] = PILOT_CODES) -> dict:
    """The whole analysis block for graph/data.js. Pure; deterministic; no I/O.

    Pilots and engagement outliers are excluded from typing but stay in the per-construct
    stats, where their scores are real data.
    """
    excluded = {s["subject_code"]: "pilot / operator dry-run, not a study subject"
                for s in sorted(subjects, key=lambda x: x["subject_code"])
                if s["subject_code"] in pilots}
    excluded.update({c: r for c, r in engagement_outliers(subjects).items() if c not in excluded})
    typed = sorted((s for s in subjects if s["subject_code"] not in excluded),
                   key=lambda s: s["subject_code"])
    study = [s for s in subjects if s["subject_code"] not in pilots]
    # Pilots are dry-runs and never belong in a distribution. Engagement outliers do stay:
    # they were excluded from *typing* for want of shape, but their scores are real (spec §2.5).
    split = constants_and_discriminators(study)

    groups: list[dict] = []
    order: list[str] = []
    if len(typed) >= 2:
        profiles = {s["subject_code"]: zprofile({c: score_of(s, c) for c in CONSTRUCTS}) for s in typed}
        merges = linkage(profiles)
        order = seriate(merges)
        by_code = {s["subject_code"]: s for s in typed}
        for members in cut(merges, min(k, len(typed))):
            mean_profile = {c: round(st.mean([score_of(by_code[m], c) for m in members]), 2)
                            for c in CONSTRUCTS}
            ranked = sorted(CONSTRUCTS, key=lambda c: -mean_profile[c])
            groups.append({"members": list(members), "n": len(members),
                           "mean_profile": mean_profile,
                           "high": ranked[:3], "low": ranked[-3:][::-1]})
    elif typed:
        order = [typed[0]["subject_code"]]

    return {"order": order, "groups": groups,
            "constants": split["constants"], "discriminators": split["discriminators"],
            "stats": split["stats"], "bank_coverage": bank_coverage(bank),
            "excluded": excluded, "k": len(groups),
            "n_typed": len(typed), "n_total": len(subjects)}
