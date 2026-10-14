import math

import pandas as pd
import pytest

from shared.preprocess import derive, ensure_schema_columns


def _row(**kw):
    base = dict(imo=9_000_001, year=2025, ship_type="tanker", co2_t=10_000.0, berth_co2_t=2_000.0, co2_per_nm_kg=200.0,
                sea_hours=2_500.0, dwt=100_000.0, build_year=2015, fuel_t=3_150.0, co2_intra_eu_t=4_000.0, source_version="t")
    base.update(kw)
    return ensure_schema_columns(pd.DataFrame([base]))


def test_derive_formulas():
    d = derive(_row()).iloc[0]
    assert d.distance_nm == pytest.approx(10_000 * 1000 / 200)          # 50,000 nm (역산)
    assert d.sea_eff_kg_nm == pytest.approx(8_000 * 1000 / 50_000)      # 정박 뺀 해상 효율 160
    assert d.avg_speed_kn == pytest.approx(50_000 / 2_500)              # 20 kn
    assert d.berth_share == pytest.approx(0.2)
    assert d.eu_share == pytest.approx(0.4)
    assert d.co2_per_fuel == pytest.approx(10_000 / 3_150)
    assert d.alt_fuel == 0.0
    assert d.age == 10
    assert d.ln_dwt == pytest.approx(math.log(100_000))
    assert d.cii_attained == pytest.approx(10_000 * 1e6 / (100_000 * 50_000))


def test_distance_input_path_matches_reported_path():
    """API(거리 입력)와 MRV(거리당 CO₂ 입력)가 같은 해상 효율을 낸다."""
    a = derive(_row()).iloc[0]
    b = derive(_row(distance_nm=a.distance_nm).drop(columns="co2_per_nm_kg")).iloc[0]
    assert b.sea_eff_kg_nm == a.sea_eff_kg_nm
    assert b.avg_speed_kn == a.avg_speed_kn


def test_alt_fuel_flags_low_co2_per_fuel():
    d = derive(_row(fuel_t=10_000 / 2.75)).iloc[0]
    assert d.alt_fuel == pytest.approx(3.11 - 2.75)


def test_derive_does_not_mutate_input():
    r = _row()
    before = r.copy()
    derive(r)
    pd.testing.assert_frame_equal(r, before)
