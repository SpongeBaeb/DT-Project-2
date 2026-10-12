"""예측 피처 (models/forecast/features.py): 손으로 계산한 값, 연속하지 않은 해, 품질 표시 경계, 미래 누수·한 척 독립성.

팀 원본과의 수치 대조는 experiments/A-1_forecast_features/verify_features.py (실제 데이터, 수동 실행).
"""
import numpy as np
import pandas as pd
import pytest

from models.forecast.features import NUM, build_features, delta_clip_bounds, make_pairs

LO, HI = -0.5, 0.45


def ship(imo, years, levels, **kw):
    n = len(years)
    d = pd.DataFrame({
        "imo": imo, "year": years, "ship_type": kw.get("ship_type", "tanker"), "age": 10, "dwt": 50000.0, "gt": 30000.0,
        "ice_class": None, "hsc_proxy": False, "sea_eff_kg_nm": levels, "fuel_t": 5000.0, "distance_nm": 30000.0,
        "sea_hours": 3000.0, "avg_speed_kn": 10.0, "berth_share": 0.05, "eu_share": 0.5,
        "cii_ratio_2026basis": kw.get("cii", 1.0), "mm_a": True, "mm_b": False, "mm_c": False, "co2_recovered": False,
        "co2_parts_bad": False, "cii_type_changed": False, "avg_load": 40000.0, "avg_load_invalid": False, "avg_load_basis": "mass",
    })
    for k, v in kw.items():
        if k in d.columns:
            d[k] = v
    return d


def test_prev_change_trend_and_flags():
    f = build_features(ship(1, [2018, 2019, 2020, 2021], [100, 110, 121, 133.1]), (LO, HI)).set_index("year")
    r = np.log(1.1)
    assert np.isnan(f.loc[2018, "delta_prev_clip"]) and f.loc[2019, "delta_prev_clip"] == pytest.approx(r)
    assert np.isnan(f.loc[2019, "trend3"]) and f.loc[2020, "trend3"] == pytest.approx(r) and f.loc[2021, "trend3"] == pytest.approx(r)
    assert f["has_prev"].tolist() == [0, 1, 1, 1] and f["has_trend3"].tolist() == [0, 0, 1, 1]
    assert f["n_prev"].tolist() == [0, 1, 2, 3]
    assert f.loc[2021, "dev_own"] == pytest.approx(np.log(133.1) - np.mean(np.log([100, 110, 121])))
    assert f.loc[2021, "vol_past"] == pytest.approx(r)                      # 변화 폭이 매번 같으므로
    assert f["covid_t"].tolist() == [0, 0, 1, 1] and f["covid_next"].tolist() == [0, 1, 1, 0]


def test_prev_change_is_clipped():
    f = build_features(ship(1, [2018, 2019], [100, 1000]), (LO, HI)).set_index("year")
    assert f.loc[2019, "delta_prev_clip"] == HI and f.loc[2019, "vol_past"] == HI


def test_missing_year_breaks_the_chain():
    f = build_features(ship(1, [2018, 2019, 2021], [100, 110, 133.1]), (LO, HI)).set_index("year")
    assert f.loc[2019, "has_prev"] == 1
    assert f.loc[2021, "has_prev"] == 0 and np.isnan(f.loc[2021, "trend3"]) and np.isnan(f.loc[2021, "speed_chg"])   # 2020 이 없어 연속이 아님


@pytest.mark.parametrize("col, kw, flagged", [
    ("q_short_sea", {"sea_hours": 335.9}, 1), ("q_short_sea", {"sea_hours": 336.0}, 0),
    ("q_speed_odd", {"avg_speed_kn": 3.0}, 1), ("q_speed_odd", {"avg_speed_kn": 3.01}, 0),
    ("q_speed_odd", {"avg_speed_kn": 26.0}, 1), ("q_speed_odd", {"avg_speed_kn": 25.0}, 0),
    ("q_speed_odd", {"avg_speed_kn": 33.0, "hsc_proxy": True}, 0),          # 고속선은 빠른 게 정상
])
def test_quality_flag_boundaries(col, kw, flagged):
    assert build_features(ship(1, [2020], [100.0], **kw), (LO, HI))[col].iloc[0] == flagged


def test_level_out_flags_extreme_cii_within_type_and_year():
    ships = pd.concat([ship(i, [2020], [100.0], cii=1.0 + 0.01 * i) for i in range(1, 30)] + [ship(99, [2020], [100.0], cii=9.0)])
    f = build_features(ships, (LO, HI)).set_index("imo")
    assert f.loc[99, "q_level_out"] == 1 and f.drop(index=99)["q_level_out"].sum() == 0
    assert f.loc[99, "level_pct"] == 1.0 and f.loc[1, "level_pct"] == pytest.approx(1 / 30)


def test_parts_bad_blanks_the_shares_like_the_team_pipeline():
    f = build_features(ship(1, [2020], [100.0], co2_parts_bad=True), (LO, HI))
    assert np.isnan(f["berth_share"].iloc[0]) and np.isnan(f["intra_eu_share"].iloc[0]) and f["co2_parts_bad"].iloc[0] == 1


def test_load_features_use_only_confirmed_mass_basis():
    f = build_features(ship(1, [2019, 2020], [100.0, 100.0], avg_load=[30000.0, 36000.0]), (LO, HI)).set_index("year")
    assert f.loc[2020, "load_factor"] == pytest.approx(36000 / 50000) and f.loc[2020, "load_chg"] == pytest.approx(np.log(1.2))
    v = build_features(ship(1, [2020], [100.0], avg_load_basis="volume"), (LO, HI))
    assert np.isnan(v["load_factor"].iloc[0])


def test_pairs_horizon_and_clip_bounds():
    f = build_features(ship(1, [2018, 2019, 2020, 2021], [100, 110, 121, 133.1]), (LO, HI))
    p1, p2 = make_pairs(f, 1), make_pairs(f, 2)
    assert len(p1) == 3 and len(p2) == 2 and p1["target_year"].tolist() == [2019, 2020, 2021]
    assert p1["delta"].tolist() == pytest.approx([np.log(1.1)] * 3) and p2["delta"].tolist() == pytest.approx([2 * np.log(1.1)] * 2)
    assert p1["covid_next"].tolist() == [0, 1, 1]
    lo, hi = delta_clip_bounds(p1, train_until_year=2020)
    assert lo == pytest.approx(np.log(1.1)) and hi == pytest.approx(np.log(1.1))


def test_no_future_leak_and_one_ship_independence():
    many = pd.concat([ship(1, [2018, 2019, 2020, 2021], [100, 130, 120, 150]), ship(2, [2018, 2019, 2020, 2021], [200, 190, 215, 210], cii=1.3)])
    full = build_features(many, (LO, HI))
    past = build_features(many[many["year"] <= 2020], (LO, HI))
    pd.testing.assert_frame_equal(full[full["year"] <= 2020].reset_index(drop=True), past, rtol=0, atol=1e-12)        # 미래 연도를 지워도 같다
    cross = {"level_pct", "q_level_out"}                                         # 같은 해 다른 배와 비교하는 값은 한 척만으로 못 정한다
    alone = build_features(many[many["imo"] == 1], (LO, HI))
    cols = [c for c in NUM if c not in cross]
    pd.testing.assert_frame_equal(full[full["imo"] == 1][cols].reset_index(drop=True), alone[cols].reset_index(drop=True), rtol=0, atol=1e-12)
