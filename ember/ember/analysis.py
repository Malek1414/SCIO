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
