import pytest

from ember.analysis import FLAT_SD, shape_distance, zprofile
from ember.constructs import CONSTRUCTS


def _scores(**kw) -> dict[str, int]:
    base = {c: 4 for c in CONSTRUCTS}
    base.update(kw)
    return base


def test_zprofile_is_in_construct_order_and_centred():
    z = zprofile(_scores(F1=7, G3=1))
    assert len(z) == len(CONSTRUCTS)
    assert z[CONSTRUCTS.index("F1")] > 0 > z[CONSTRUCTS.index("G3")]
    assert sum(z) == pytest.approx(0.0, abs=1e-9)


def test_flat_profile_is_all_zeros_not_a_crash():
    assert zprofile(_scores()) == [0.0] * len(CONSTRUCTS)


def test_identical_shapes_have_zero_distance():
    a = zprofile(_scores(F1=7, F2=6, G3=1))
    assert shape_distance(a, a) == pytest.approx(0.0, abs=1e-9)


def test_same_shape_different_level_is_still_zero_distance():
    """The whole point: overall level must not drive typing."""
    low = zprofile({"F1": 3, "F2": 2, "F3": 1, "C1": 2, "C2": 1, "C3": 3, "G1": 1, "G2": 2, "G3": 3})
    high = zprofile({"F1": 6, "F2": 5, "F3": 4, "C1": 5, "C2": 4, "C3": 6, "G1": 4, "G2": 5, "G3": 6})
    assert shape_distance(low, high) == pytest.approx(0.0, abs=1e-9)


def test_opposite_shapes_have_distance_two():
    a = zprofile(_scores(F1=7, G3=1))
    b = zprofile(_scores(F1=1, G3=7))
    assert shape_distance(a, b) == pytest.approx(2.0, abs=1e-9)


def test_flat_profile_distance_is_one_not_nan():
    assert shape_distance(zprofile(_scores()), zprofile(_scores(F1=7))) == 1.0


def test_flat_sd_constant_is_exposed():
    assert FLAT_SD == 0.5
