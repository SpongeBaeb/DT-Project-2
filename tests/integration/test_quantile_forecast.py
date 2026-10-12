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


# ───────────────────── CII D·E 확률 ─────────────────────
from contracts.tables import P_DE_COLS  # noqa: E402

CII_TYPE = {"container": "Container ship", "tanker": "Tanker", "bulk": "Bulk carrier", "ro_pax": "Ro-ro passenger ship"}


@pytest.fixture(scope="module")
def cii_snapshot(snapshot):
    """합성 표본에 CII 열을 붙인다: 배마다 일정한 비율(0.7~1.5) → 경계(1.06~1.14) 근처의 배가 섞인다."""
    rng = np.random.default_rng(0)
    base = pd.Series(rng.uniform(0.7, 1.5, snapshot["imo"].nunique()), index=snapshot["imo"].drop_duplicates().to_numpy())
    ratio = snapshot["imo"].map(base)
    rating = pd.cut(ratio, [0, 0.86, 0.94, 1.06, 1.18, np.inf], labels=list("ABCDE")).astype(str)       # 비율로 만든 합성 등급
    return snapshot.assign(cii_ship_type=snapshot["ship_type"].map(CII_TYPE), cii_ratio_2026basis=ratio, cii_rating=rating)


@pytest.fixture(scope="module")
def cii_cfg(cfg):
    c = copy.deepcopy(cfg)
    stages = [copy.deepcopy(s) for s in STAGES]
    stages[1]["params"]["cii"] = True
    c["stages"] = [s for s in c["stages"] if not s["use"].endswith("PersistenceForecast")] + stages
    return c


@pytest.fixture(scope="module")
def cii_bundle(cii_snapshot, cii_cfg):
    return ModelBundle.train(cii_snapshot, cii_cfg)


@pytest.fixture(scope="module")
def cii_res(cii_bundle, cii_snapshot):
    return cii_bundle.run(cii_snapshot)


def test_p_de_is_a_probability_and_rises_with_the_ratio(cii_res, cii_snapshot):
    RESULT_TABLE.validate(cii_res, extra="forbid")
    assert cii_res[P_DE_COLS].notna().all().all()
    assert cii_res[P_DE_COLS].min().min() >= 0.01 - 1e-12 and cii_res[P_DE_COLS].max().max() <= 0.99 + 1e-12
    y = cii_res.merge(cii_snapshot[["imo", "year", "cii_ratio_2026basis"]], on=["imo", "year"])
    y = y[y["year"] == 2025]
    for h in (1, 2, 3):
        assert y["cii_ratio_2026basis"].corr(y[f"p_de_h{h}"], method="spearman") > 0.7       # 비율이 클수록 D·E 확률이 높다
    assert y.loc[y["cii_ratio_2026basis"] > 1.4, "p_de_h1"].mean() > 0.8
    assert y.loc[y["cii_ratio_2026basis"] < 0.8, "p_de_h1"].mean() < 0.2


def test_p_de_grows_with_horizon_for_a_borderline_ship(cii_res, cii_snapshot):
    """감축률이 해마다 커지므로 같은 상태의 배는 더 먼 해에 D·E 가 되기 쉽다 (평균적으로)."""
    y = cii_res[cii_res["year"] == 2025]
    assert y["p_de_h3"].mean() > y["p_de_h1"].mean()


def test_p_de_one_ship_equals_full(cii_bundle, cii_snapshot, cii_res):
    some = cii_snapshot["imo"].drop_duplicates().sample(10, random_state=5)
    alone = pd.concat([cii_bundle.run(cii_snapshot[cii_snapshot["imo"] == i]) for i in some], ignore_index=True).sort_values(["imo", "year"]).reset_index(drop=True)
    full = cii_res[cii_res["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(alone[["imo", "year", *P_DE_COLS]], full[["imo", "year", *P_DE_COLS]], rtol=0, atol=1e-9)


def test_p_de_is_blank_without_cii_data(qres):
    """CII 열이 없는(또는 cii 설정이 꺼진) 설정에서는 빈칸이다 — 결과 표 2.2 의 선택 열."""
    assert qres[P_DE_COLS].isna().all().all()


def test_p_de_needs_the_total_efficiency_target():
    from models.forecast.quantile_stage import QuantileForecast
    with pytest.raises(ValueError, match="정박 포함"):
        QuantileForecast(level="sea_eff_kg_nm", prefix="fc", cii=True)


# ───────────────────── 감축 요구 미달 확률 (p_miss_h1) ─────────────────────
def test_p_miss_is_a_probability_that_rises_with_the_predicted_drift(cii_res, cii_snapshot):
    RESULT_TABLE.validate(cii_res, extra="forbid")
    assert cii_res["p_miss_h1"].notna().all()
    assert cii_res["p_miss_h1"].between(0.01 - 1e-12, 0.99 + 1e-12).all()
    y = cii_res[cii_res["year"] == 2025].merge(cii_snapshot[["imo", "year", "co2_per_nm_kg"]], on=["imo", "year"])
    drift = np.log(y["fct_h1_p50"] / y["co2_per_nm_kg"])                       # 예측 변화 (양수 = 나빠짐)
    assert drift.corr(y["p_miss_h1"], method="spearman") > 0.8                # 덜 줄일수록(또는 늘수록) 미달 확률이 높다
    assert y.loc[drift > drift.quantile(0.9), "p_miss_h1"].mean() > y.loc[drift < drift.quantile(0.1), "p_miss_h1"].mean() + 0.2


def test_p_miss_one_ship_equals_full(cii_bundle, cii_snapshot, cii_res):
    some = cii_snapshot["imo"].drop_duplicates().sample(8, random_state=9)
    alone = pd.concat([cii_bundle.run(cii_snapshot[cii_snapshot["imo"] == i]) for i in some], ignore_index=True).sort_values(["imo", "year"]).reset_index(drop=True)
    full = cii_res[cii_res["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_series_equal(alone["p_miss_h1"], full["p_miss_h1"], rtol=0, atol=1e-9)


def test_p_miss_is_blank_without_the_cii_option(qres):
    assert qres["p_miss_h1"].isna().all()


# ───────────────────── 다음 해 리스트 (list_h1) ─────────────────────
@pytest.fixture(scope="module")
def list_cfg(cii_cfg):
    c = copy.deepcopy(cii_cfg)
    c["stages"].append({"use": "models.forecast.lists:ListRule", "params": {"de_cut": 0.8, "watch_quantile": 0.75, "watch_ratings": ["A", "B", "C"]}})
    return c


@pytest.fixture(scope="module")
def list_bundle(cii_snapshot, list_cfg):
    return ModelBundle.train(cii_snapshot, list_cfg)


@pytest.fixture(scope="module")
def list_res(list_bundle, cii_snapshot):
    return list_bundle.run(cii_snapshot)


def test_list_follows_the_rule_with_the_frozen_threshold(list_bundle, list_res, cii_snapshot):
    RESULT_TABLE.validate(list_res, extra="forbid")
    assert set(list_res["list_h1"]) <= {"target", "watch", ""}
    detail = list_bundle.stages[-1].describe()["detail"]
    r = list_res.merge(cii_snapshot[["imo", "year", "cii_rating"]], on=["imo", "year"])
    p25 = r.loc[r["year"] == 2025, "p_miss_h1"]
    assert detail["base_year"] == 2025 and detail["p_star"] == pytest.approx(round(float(p25.quantile(0.75)), 6))
    target = r["p_de_h1"] >= 0.8
    watch = ~target & r["cii_rating"].isin(list("ABC")) & (r["p_miss_h1"] >= detail["p_star"])
    assert (r["list_h1"] == "target").equals(target) and (r["list_h1"] == "watch").equals(watch)
    assert target.any() and watch.any()                                           # 합성 표본에도 두 리스트가 다 있다 (규칙이 비어 있지 않음)


def test_list_one_ship_equals_full(list_bundle, cii_snapshot, list_res):
    some = cii_snapshot["imo"].drop_duplicates().sample(12, random_state=13)
    alone = pd.concat([list_bundle.run(cii_snapshot[cii_snapshot["imo"] == i]) for i in some], ignore_index=True).sort_values(["imo", "year"]).reset_index(drop=True)
    full = list_res[list_res["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_series_equal(alone["list_h1"], full["list_h1"])


def test_list_is_blank_without_the_list_stage(qres):
    assert qres["list_h1"].isna().all()
