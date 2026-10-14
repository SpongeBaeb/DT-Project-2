import pytest

from models.physics import speed_change_factor, what_if_speed


def test_no_change_is_identity():
    assert speed_change_factor(0, 0.7) == pytest.approx(1.0)


def test_slow_steaming_reduces_per_distance_fuel():
    assert what_if_speed(400, -10, 0.75) < 400


def test_main_engine_only_follows_square_law():
    assert speed_change_factor(-10, 0.999999) == pytest.approx(0.9**2, rel=1e-5)


def test_rejects_bad_share():
    with pytest.raises(ValueError):
        speed_change_factor(-10, 1.0)
