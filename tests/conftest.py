from pathlib import Path
import pytest
import yaml

from ember.constructs import CONSTRUCTS


def write_mini_bank(d: Path) -> None:
    """A minimal valid bank: 3 candidates per slot 2–6, one default each, all 9 rubric entries."""
    opener = {
        "text": "Think of someone you know who's clearly going to make it. What do they do differently?",
        "rephrase": "Someone you know who's going to make it. What's different about them?",
        "fallback_take_home": "What would you have to stop doing to become that person?",
    }
    cluster = {2: "fire", 3: "fire", 4: "fire", 5: "compass", 6: "ground"}
    target = {2: "F1", 3: "F2", 4: "F3", 5: "C1", 6: "G1"}
    cands = []
    for slot in range(2, 7):
        for i, letter in enumerate("abc"):
            cands.append({
                "id": f"S{slot}-{letter}", "slot": slot, "cluster": cluster[slot],
                "targets": [target[slot]], "threat": min(7, slot + i),
                "framing": "counterfactual-removal",
                "prerequisites": [] if (slot == 2 or letter != "c") else ["family"],
                "default": letter == "a",
                "text": f"What happens at slot {slot} option {letter}?",
                "rephrase": f"What is slot {slot} option {letter} like?",
            })
    rubric = [{
        "construct": c, "name": f"Construct {c}", "inverse": c == "F3",
        "anchors": [{"score": s, "description": f"{c} level {s}", "exemplar": f"{c} example {s}"} for s in (1, 4, 7)],
    } for c in CONSTRUCTS]
    (d / "opener.yaml").write_text(yaml.safe_dump(opener, sort_keys=False))
    (d / "questions.yaml").write_text(yaml.safe_dump({"candidates": cands}, sort_keys=False))
    (d / "rubric.yaml").write_text(yaml.safe_dump({"rubric": rubric}, sort_keys=False))


@pytest.fixture
def mini_bank_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bank"
    d.mkdir()
    write_mini_bank(d)
    return d


@pytest.fixture
def mini_bank(mini_bank_dir):
    from ember.bank import load_bank
    return load_bank(mini_bank_dir)
