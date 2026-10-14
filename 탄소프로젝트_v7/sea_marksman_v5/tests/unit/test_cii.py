"""CII D·E 확률의 규칙 부분 (models/forecast/cii.py): 등급 경계, 감축률, 임계값 수식."""
import numpy as np
import pandas as pd
import pytest

from models.forecast import cii


def frame(t="Tanker", ratio=1.0, dwt=100_000.0, gt=60_000.0):
    return pd.DataFrame({"cii_ship_type": [t], "cii_ratio_2026basis": [ratio], "dwt": [dwt], "gt": [gt]})


@pytest.mark.parametrize("t, dwt, gt, d3", [
    ("Tanker", 1e5, 5e4, 1.08), ("Bulk carrier", 8e4, 4e4, 1.06), ("Container ship", 6e4, 4e4, 1.07),
    ("Ro-ro passenger ship", 5e3, 3e4, 1.14), ("Cruise passenger ship", 5e3, 9e4, 1.06),
    ("Gas carrier", 7e4, 5e4, 1.12), ("Gas carrier", 3e4, 2e4, 1.06),            # 가스선은 65,000dwt 를 경계로 표가 다르다
])
def test_d_boundary_matches_the_imo_table(t, dwt, gt, d3):
    df = frame(t, dwt=dwt, gt=gt)
    assert cii.d_boundary(df["cii_ship_type"], df["dwt"], df["gt"])[0] == pytest.approx(d3)


def test_unknown_or_missing_type_gives_nan():
    df = pd.DataFrame({"cii_ship_type": ["Submarine", None, np.nan], "dwt": [1.0, 1.0, 1.0], "gt": [1.0, 1.0, 1.0]})
    assert np.isnan(cii.d_boundary(df["cii_ship_type"], df["dwt"], df["gt"])).all()


def test_reduction_factors_include_2027_and_2028():
    z = cii.z_pct()
    assert z[2026] == 11 and z[2027] == 13.625 and z[2028] == 16.25 and z[2019] == 0


def test_threshold_for_the_basis_year_is_just_the_boundary_over_the_ratio():
    """2026 기준 비율 r 인 배가 2026 에 D·E 가 되려면 Δ ≥ ln(d3 / r)."""
    for r in (0.8, 1.0, 1.05, 1.3):
        thr = cii.threshold(frame(ratio=r), [2026])[0]
        assert thr == pytest.approx(np.log(1.08 / r))


def test_threshold_tightens_with_later_target_years():
    """감축률이 커질수록 기준선이 낮아져 같은 배가 D·E 가 되기 쉽다 → 임계값이 내려간다."""
    thr = cii.threshold(frame(ratio=1.0), [2026, 2027, 2028])
    assert thr[0] > thr[1] > thr[2]
    assert thr[2] == pytest.approx(np.log(1.08) + np.log((1 - 0.1625) / (1 - 0.11)))


def test_unknown_target_year_or_missing_ratio_gives_nan():
    assert np.isnan(cii.threshold(frame(ratio=1.0), [2035])[0])
    assert np.isnan(cii.threshold(frame(ratio=np.nan), [2026])[0])
    assert np.isnan(cii.threshold(frame(ratio=0.0), [2026])[0])


def test_miss_threshold_is_the_next_years_required_reduction():
    t = cii.miss_threshold([2025, 2026, 2024, 2018])
    assert t[0] == pytest.approx(np.log((1 - 0.11) / (1 - 0.09)))                    # 2025 → 2026: 기준선이 연 2.2% 내려감
    assert t[1] == pytest.approx(np.log((1 - 0.13625) / (1 - 0.11)))
    assert t[2] == pytest.approx(np.log((1 - 0.09) / (1 - 0.07)))
    assert t[3] == pytest.approx(0.0)                                                # 2018 → 2019: 표 첫 해 이전은 Z=0 (팀과 같음)
    assert (t[:3] < 0).all()                                                         # 요구가 있는 해는 임계값이 음수 (줄여야 함)


def test_miss_threshold_is_nan_when_the_next_reduction_is_unknown():
    assert np.isnan(cii.miss_threshold([2028])[0]) and np.isnan(cii.miss_threshold([2035])[0])
