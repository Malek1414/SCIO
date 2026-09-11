from ember.constructs import CLUSTERS, CONSTRUCTS, CLUSTER_OF, TAGS, FRAMINGS, signal_for


def test_nine_constructs_in_three_clusters():
    assert CONSTRUCTS == ("F1", "F2", "F3", "C1", "C2", "C3", "G1", "G2", "G3")
    assert set(CLUSTERS) == {"fire", "compass", "ground"}
    assert CLUSTER_OF["F2"] == "fire" and CLUSTER_OF["G3"] == "ground"


def test_tag_and_framing_vocab():
    assert "named-project" in TAGS and "faith" in TAGS
    assert "cost-already-paid" in FRAMINGS and "empty-room" in FRAMINGS


def test_signal_thresholds():
    assert signal_for(0, 0, False) == "low"
    assert signal_for(1, 1, False) == "low"
    assert signal_for(2, 1, False) == "med"
    assert signal_for(3, 1, False) == "med"        # 3 quotes but one answer
    assert signal_for(3, 2, False) == "high"
    assert signal_for(5, 3, True) == "low"         # skipped always low
