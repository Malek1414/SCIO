from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError

from ember.bank import Candidate, Bank, load_bank
from tests.conftest import write_mini_bank


def test_load_mini_bank(mini_bank):
    assert mini_bank.opener.text.startswith("Think of someone")
    assert len(mini_bank.candidates) == 15
    assert set(mini_bank.rubric) == {"F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3"}


def test_for_slot_and_default(mini_bank):
    assert [c.id for c in mini_bank.for_slot(3)] == ["S3-a", "S3-b", "S3-c"]
    assert mini_bank.default_for(3).id == "S3-a"
    assert mini_bank.by_id("S5-b").cluster == "compass"


def test_slot7_draws_unused_5_and_6(mini_bank):
    ids = {c.id for c in mini_bank.for_slot(7, used={"S5-a", "S6-b"})}
    assert ids == {"S5-b", "S5-c", "S6-a", "S6-c"}
    assert mini_bank.default_for(7, used={"S6-a"}).id == "S5-a"
    assert mini_bank.default_for(7, used={"S5-a", "S5-b", "S5-c", "S6-a", "S6-b", "S6-c"}) is None


def _cand(**over):
    base = dict(id="X", slot=3, cluster="fire", targets=["F2"], threat=5, framing="cost-already-paid",
                prerequisites=[], default=False, text="What did it cost you?", rephrase="What was the cost?")
    base.update(over)
    return base


def test_candidate_rejects_yes_no_question():
    with pytest.raises(ValidationError, match="yes/no"):
        Candidate(**_cand(text="Do you regret it?"))


def test_candidate_rejects_cluster_target_mismatch():
    with pytest.raises(ValidationError, match="cluster"):
        Candidate(**_cand(cluster="compass"))


def test_candidate_rejects_unknown_tag_or_framing():
    with pytest.raises(ValidationError):
        Candidate(**_cand(prerequisites=["astrology"]))
    with pytest.raises(ValidationError):
        Candidate(**_cand(framing="mind-reading"))


def test_slot2_prerequisites_must_be_empty():
    with pytest.raises(ValidationError, match="slot 2"):
        Candidate(**_cand(slot=2, targets=["F1"], prerequisites=["money"]))


def test_bank_requires_one_default_per_slot(tmp_path: Path):
    write_mini_bank(tmp_path)
    q = yaml.safe_load((tmp_path / "questions.yaml").read_text())
    for c in q["candidates"]:
        if c["id"] == "S4-b":
            c["default"] = True
    (tmp_path / "questions.yaml").write_text(yaml.safe_dump(q))
    with pytest.raises(ValidationError, match="slot 4"):
        load_bank(tmp_path)


def test_bank_requires_three_candidates_per_slot(tmp_path: Path):
    write_mini_bank(tmp_path)
    q = yaml.safe_load((tmp_path / "questions.yaml").read_text())
    q["candidates"] = [c for c in q["candidates"] if c["id"] != "S6-c"]
    (tmp_path / "questions.yaml").write_text(yaml.safe_dump(q))
    with pytest.raises(ValidationError, match="slot 6"):
        load_bank(tmp_path)
