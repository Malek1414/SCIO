import pytest

from ember.analysis import cut, linkage, seriate, zprofile


def _profiles() -> dict[str, list[float]]:
    """A, B share a shape; C is their opposite. Expected: (A,B) merge first, then C."""
    a = {"F1": 7, "F2": 6, "F3": 5, "C1": 4, "C2": 4, "C3": 3, "G1": 2, "G2": 2, "G3": 1}
    b = {"F1": 6, "F2": 6, "F3": 5, "C1": 4, "C2": 3, "C3": 3, "G1": 2, "G2": 1, "G3": 1}
    c = {"F1": 1, "F2": 2, "F3": 2, "C1": 4, "C2": 4, "C3": 5, "G1": 6, "G2": 6, "G3": 7}
    return {"A": zprofile(a), "B": zprofile(b), "C": zprofile(c)}


def test_linkage_merges_the_similar_pair_first():
    m = linkage(_profiles())
    assert len(m) == 2
    assert set(m[0].left + m[0].right) == {"A", "B"}
    assert m[0].height < m[1].height


def test_last_merge_contains_everyone():
    assert set(linkage(_profiles())[-1].members) == {"A", "B", "C"}


def test_seriate_puts_similar_subjects_adjacent():
    order = seriate(linkage(_profiles()))
    assert order.index("A") - order.index("B") in (-1, 1)
    assert len(order) == 3


def test_cut_returns_k_groups():
    m = linkage(_profiles())
    assert [set(g) for g in cut(m, 2)] == [{"A", "B"}, {"C"}]
    assert len(cut(m, 3)) == 3
    assert len(cut(m, 1)) == 1


def test_cut_rejects_impossible_k():
    with pytest.raises(ValueError):
        cut(linkage(_profiles()), 4)


def test_linkage_is_deterministic_regardless_of_input_order():
    p = _profiles()
    assert linkage(p) == linkage({k: p[k] for k in reversed(list(p))})


def test_choose_k_finds_the_gap():
    """Two tight pairs far apart: the honest cut is k=2, where the height jumps."""
    from ember.analysis import choose_k
    p = {"A": zprofile({"F1": 7, "F2": 6, "F3": 5, "C1": 4, "C2": 4, "C3": 3, "G1": 2, "G2": 2, "G3": 1}),
         "B": zprofile({"F1": 6, "F2": 6, "F3": 5, "C1": 4, "C2": 3, "C3": 3, "G1": 2, "G2": 1, "G3": 1}),
         "C": zprofile({"F1": 1, "F2": 2, "F3": 2, "C1": 4, "C2": 4, "C3": 5, "G1": 6, "G2": 6, "G3": 7}),
         "D": zprofile({"F1": 1, "F2": 1, "F3": 2, "C1": 3, "C2": 4, "C3": 5, "G1": 6, "G2": 7, "G3": 7})}
    k, gap = choose_k(linkage(p))
    assert k == 2 and gap > 0


def test_choose_k_skips_cuts_that_only_peel_off_an_outlier():
    """A singleton-vs-everyone split is not a typology, however large its gap."""
    from ember.analysis import choose_k, cut
    p = {c: zprofile(s) for c, s in {
        "A": {"F1": 7, "F2": 6, "F3": 6, "C1": 4, "C2": 4, "C3": 3, "G1": 2, "G2": 2, "G3": 1},
        "B": {"F1": 6, "F2": 6, "F3": 5, "C1": 4, "C2": 3, "C3": 3, "G1": 2, "G2": 1, "G3": 1},
        "C": {"F1": 1, "F2": 2, "F3": 2, "C1": 4, "C2": 4, "C3": 5, "G1": 6, "G2": 6, "G3": 7},
        "D": {"F1": 1, "F2": 1, "F3": 2, "C1": 3, "C2": 4, "C3": 5, "G1": 6, "G2": 7, "G3": 7},
        "Z": {"F1": 4, "F2": 1, "F3": 7, "C1": 1, "C2": 7, "C3": 1, "G1": 7, "G2": 1, "G3": 4},
    }.items()}
    m = linkage(p)
    k, _ = choose_k(m)
    assert sum(1 for g in cut(m, k) if len(g) >= 2) >= 2, "cut must leave real groups, not one outlier"
