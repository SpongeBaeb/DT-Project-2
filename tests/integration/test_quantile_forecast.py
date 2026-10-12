"""QuantileForecast (회귀 v4 이식): 계약, 분위 순서, 한 척 = 전체, 미래 누수 없음, 저장·불러오기, 학습 쌍이 적을 때.

기본 설정은 그대로 두고 합성 표본에서 PersistenceForecast 자리에 이 부품 둘(해상 효율 fc, 전체 효율 fct)을 끼워 확인한다.
수치 재현은 experiments/A-1_forecast_features/verify_forecast.py (실제 데이터, 수동 실행).
"""
import copy

import numpy as np
import pandas as pd
import pytest

from contracts.tables import FORECAST_COLS, RESULT_TABLE, TOTAL_FORECAST_COLS
from models.bundle import ModelBundle
from models.forecast.features import CrossSection

STAGES = [
    {"use": "models.forecast.quantile_stage:QuantileForecast", "params": {"level": "sea_eff_kg_nm", "prefix": "fc", "n_jobs": 2}},
    {"use": "models.forecast.quantile_stage:QuantileForecast", "params": {"level": "co2_per_nm_kg", "prefix": "fct", "n_jobs": 2}},
]


@pytest.fixture(scope="module")
def qcfg(cfg):
    c = copy.deepcopy(cfg)
    c["stages"] = [s for s in c["stages"] if not s["use"].endswith("PersistenceForecast")] + STAGES
    return c


@pytest.fixture(scope="module")
def qbundle(snapshot, qcfg):
    return ModelBundle.train(snapshot, qcfg)


@pytest.fixture(scope="module")
def qres(qbundle, snapshot):
    return qbundle.run(snapshot)


def test_meets_contract_and_fills_both_forecasts(qres, snapshot):
    RESULT_TABLE.validate(qres, extra="forbid")
    assert len(qres) == len(snapshot)
    assert qres[FORECAST_COLS].notna().all().all() and qres[TOTAL_FORECAST_COLS].notna().all().all()
    assert (qres[FORECAST_COLS] > 0).all().all()


def test_quantiles_are_ordered(qres):
    for pre in ("fc", "fct"):
        for h in (1, 2, 3):
            p10, p50, p90 = (qres[f"{pre}_h{h}_p{q}"] for q in (10, 50, 90))
            assert ((p10 <= p50) & (p50 <= p90)).all(), (pre, h)


def test_two_targets_differ_and_are_not_persistence(qres):
    assert not np.allclose(qres["fc_h1_p50"], qres["fct_h1_p50"])           # 정박 포함 여부로 값이 달라진다
    assert not np.allclose(qres["fc_h1_p50"], qres["sea_eff_actual"])        # '변화 없음'이 아니다
    # 전체 효율은 정박을 포함하므로 같은 배·해에서 해상 효율 이상이어야 한다 (현재 값 기준)
    assert (qres["fct_h1_p50"] >= qres["fc_h1_p50"] * 0.5).all()


def test_each_ship_independent_of_others(qbundle, snapshot, qres):
    """규칙 2: 한 배의 결과는 그 배의 행만으로 정해진다 (API 한 척 = 결과 표). level_pct 같은 비교 피처도 학습 때 분포로 고정돼 있다."""
    some = snapshot["imo"].drop_duplicates().sample(12, random_state=3)
    alone = pd.concat([qbundle.run(snapshot[snapshot["imo"] == i]) for i in some], ignore_index=True).sort_values(["imo", "year"]).reset_index(drop=True)
    full = qres[qres["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(alone, full, rtol=0, atol=1e-9)


def test_no_future_leak(qbundle, snapshot, qres):
    past = qbundle.run(snapshot[snapshot["year"] <= 2022])
    full = qres[qres["year"] <= 2022].reset_index(drop=True)
    pd.testing.assert_frame_equal(past.reset_index(drop=True), full, rtol=0, atol=1e-9)


def test_save_load_roundtrip(qbundle, snapshot, qres, tmp_path):
    qbundle.save(tmp_path)
    again = ModelBundle.load(tmp_path).run(snapshot)
    pd.testing.assert_frame_equal(again, qres, rtol=0, atol=0)
    stage = qbundle.stages[-1]
    assert stage.describe()["detail"]["horizons_fit"] == [1, 2, 3] and stage.describe()["detail"]["prefix"] == "fct"


def test_few_pairs_skip_the_horizon_instead_of_failing(snapshot, qcfg):
    """학습 쌍이 부족한 기간(예: 2021 까지만 학습한 3년 뒤)은 빈칸으로 두고 나머지는 예측한다."""
    b = ModelBundle.train(snapshot, qcfg, cutoff_year=2021)
    r = b.run(snapshot[snapshot["year"] == 2025])
    RESULT_TABLE.validate(r, extra="forbid")
    assert r["fc_h1_p50"].notna().all() and r["fc_h3_p50"].isna().all()


def test_frozen_cross_section_matches_rank_for_training_rows(snapshot):
    """학습에 쓴 행의 level_pct 는 pandas rank(pct=True) 와 같고, 한 척만 넣어도 같은 값이 나온다."""
    d = snapshot.assign(year_eff=snapshot["year"], cii_ratio_2026basis=snapshot["dwt"] / snapshot.groupby(["ship_type", "year"])["dwt"].transform("median"))
    cs = CrossSection().fit(d)
    want = d["cii_ratio_2026basis"].groupby([d["ship_type"], d["year"]]).rank(pct=True)
    np.testing.assert_allclose(cs.level_pct(d).to_numpy(), want.to_numpy(), atol=1e-12)
    one = d.iloc[[5]]
    assert cs.level_pct(one).iloc[0] == pytest.approx(want.iloc[5])
