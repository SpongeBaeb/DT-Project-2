"""모델 묶음 전체가 약속을 지키는지. 부품을 바꿔 끼운 뒤 이 테스트가 통과하면 다른 팀원 코드와 맞물린다."""
import numpy as np
import pandas as pd
import pytest

from contracts.tables import CONTRIB_COLS, FORECAST_COLS, RESULT_TABLE
from models.bundle import ModelBundle


def test_result_table_meets_contract(results, snapshot):
    RESULT_TABLE.validate(results, extra="forbid")
    assert len(results) == len(snapshot)


def test_cause_bars_sum_to_gap(results):
    total = results[CONTRIB_COLS].sum(axis=1)
    target = np.log(results["sea_eff_actual"] / results["sea_eff_peer_median"])
    assert (total - target).abs().max() < 1e-9


def test_forecast_quantiles_ordered(results):
    for h in (1, 2, 3):
        p10, p50, p90 = (results[f"fc_h{h}_p{q}"] for q in (10, 50, 90))
        ok = p10.isna() | ((p10 <= p50) & (p50 <= p90))
        assert ok.all()


def test_each_ship_independent_of_others(bundle, snapshot, results):
    """규칙 2: 한 배의 결과는 그 배의 행만으로 정해진다 (API 한 척 = 결과 표)."""
    some = snapshot["imo"].drop_duplicates().sample(15, random_state=0)
    alone = pd.concat([bundle.run(snapshot[snapshot["imo"] == i]) for i in some], ignore_index=True)
    full = results[results["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(alone.sort_values(["imo", "year"]).reset_index(drop=True), full, rtol=0, atol=1e-9)


def test_no_future_leak(bundle, snapshot, results):
    """규칙 3: 미래 연도를 지워도 과거 연도 결과가 같다."""
    past = snapshot[snapshot["year"] <= 2022]
    r = bundle.run(past)
    full = results[results["year"] <= 2022].reset_index(drop=True)
    pd.testing.assert_frame_equal(r.reset_index(drop=True), full, rtol=0, atol=1e-9)


def test_save_load_roundtrip(bundle, snapshot, results, tmp_path):
    bundle.save(tmp_path)
    again = ModelBundle.load(tmp_path).run(snapshot)
    pd.testing.assert_frame_equal(again, results, rtol=0, atol=0)


def test_cutoff_trains_only_on_past(snapshot, cfg):
    b = ModelBundle.train(snapshot, cfg, cutoff_year=2023)
    assert max(b.meta["train_years"]) == 2023
    r = b.run(snapshot[snapshot["year"] == 2025])
    assert r["warnings"].str.contains("학습 연도 밖").all()


def test_unknown_ship_type_rejected(bundle, snapshot):
    bad = snapshot.head(1).copy()
    bad["ship_type"] = "submarine"
    with pytest.raises(ValueError, match="학습에 없는 선종"):
        bundle.run(bad)


def test_story_ships_are_flagged(results, snapshot):
    """합성 표본의 사례 배가 의도한 신호를 받는지 (뼈대가 끝까지 이어졌다는 증거)."""
    name = snapshot.groupby("imo")["name"].last()
    last = results.sort_values("year").groupby("imo").last()
    assert last.loc[name[name == "TIGANI"].index[0], "sig_berth"]
    assert last.loc[name[name == "NEXUS"].index[0], "sig_report"]
    assert last.loc[name[name == "LNG PIONEER"].index[0], "sig_fuel"]
    assert results["sig_special"].any()
    assert not results[FORECAST_COLS].isna().all().any()
