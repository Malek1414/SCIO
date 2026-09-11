"""Construct ids, clusters, controlled vocabularies, and the signal rule (spec §3, §5.3)."""

CLUSTERS: dict[str, tuple[str, ...]] = {
    "fire": ("F1", "F2", "F3"),
    "compass": ("C1", "C2", "C3"),
    "ground": ("G1", "G2", "G3"),
}
CONSTRUCTS: tuple[str, ...] = tuple(c for cs in CLUSTERS.values() for c in cs)
CLUSTER_OF: dict[str, str] = {c: k for k, cs in CLUSTERS.items() for c in cs}

# Engine-internal tags. The observer never sees these.
TAGS: frozenset[str] = frozenset({
    "named-project", "family", "money", "health", "loss", "faith",
    "relationship", "solitude", "quit", "moved", "failure", "competition",
})

TAG_HINTS: dict[str, str] = {
    "named-project": "a specific thing they are building or working on",
    "family": "parents, siblings, children, family expectations",
    "money": "money, income, financial pressure or freedom",
    "health": "physical or mental health, their own or someone close",
    "loss": "a death, a breakup, losing something that mattered",
    "faith": "religion, God, spiritual practice or belief",
    "relationship": "a partner, close friend, or specific named person",
    "solitude": "being alone, loneliness, time by themselves",
    "quit": "quitting or leaving something — job, degree, city, project",
    "moved": "moving country or city",
    "failure": "something they tried that did not work",
    "competition": "rivalry, comparison to peers, being measured against others",
}

FRAMINGS: frozenset[str] = frozenset({
    "third-person-projection", "counterfactual-removal", "envy-locator",
    "cost-already-paid", "settled-person-read", "pressure-decision",
    "scale-of-things", "fear-of-self", "empty-room", "aftermath-not-event",
    "people-as", "discrepancy", "forking",
})


def signal_for(n_quotes: int, n_distinct_answers: int, skipped: bool) -> str:
    """Spec §3: low <2 quotes or skipped; high ≥3 quotes from ≥2 answers; else med."""
    if skipped or n_quotes < 2:
        return "low"
    if n_quotes >= 3 and n_distinct_answers >= 2:
        return "high"
    return "med"
