"""공통 잔차 모델(CommonResidualBaseline + EmpiricalBayesPosition)이 부품 규칙을 지키는지.

기본 설정은 그대로 두고, 같은 합성 표본에 이 두 부품만 바꿔 끼워 묶음 전체의 약속을 확인한다.
"""
import copy

import numpy as np
import pandas as pd
import pytest

from contracts.tables import CONTRIB_COLS, RESULT_TABLE
from models.bundle import ModelBundle
from models.common.common_residual import CommonResidualBaseline
from shared.config import load_config

SWAP = {
    "models.common.linear_baseline:LinearBaseline": {"use": "models.common.common_residual:CommonResidualBaseline"},
    "models.common.position:ShrunkPosition": {"use": "models.common.position:EmpiricalBayesPosition"},
}


@pytest.fixture(scope="module")
def cr_cfg(cfg):
    c = copy.deepcopy(cfg)
    c["stages"] = [SWAP.get(s["use"], s) for s in c["stages"]]
    return c


@pytest.fixture(scope="module")
def cr_bundle(snapshot, cr_cfg):
    return ModelBundle.train(snapshot, cr_cfg)


@pytest.fixture(scope="module")
def cr_results(cr_bundle, snapshot):
    return cr_bundle.run(snapshot)


def test_experiment_config_uses_the_new_stages():
    c = load_config("config/exp_common_residual.yaml")
    uses = [s["use"] for s in c["stages"]]
    assert "models.common.common_residual:CommonResidualBaseline" in uses
    assert "models.common.position:EmpiricalBayesPosition" in uses


def test_meets_contract_and_bars_sum_to_gap(cr_results, snapshot):
    RESULT_TABLE.validate(cr_results, extra="forbid")
    assert len(cr_results) == len(snapshot)
    total = cr_results[CONTRIB_COLS].sum(axis=1)
    target = np.log(cr_results["sea_eff_actual"] / cr_results["sea_eff_peer_median"])
    assert (total - target).abs().max() < 1e-9


def test_explains_better_than_size_only(cr_bundle, snapshot, cr_cfg):
    k = next(i for i, s in enumerate(cr_cfg["stages"]) if s["use"].endswith("CommonResidualBaseline"))
    ref = {**cr_cfg["stages"][k], "params": {"features": {"ln_dwt": "size"}}}
    specs = [*cr_cfg["stages"][:k], ref]
    r_ref = ModelBundle.train(snapshot, cr_cfg, stage_specs=specs).run(snapshot)     # 부품 일부만 → 중간 표
    r_full = ModelBundle.train(snapshot, cr_cfg, until_stage=k + 1).run(snapshot)
    err = lambda r: float(np.mean(np.log(r["sea_eff_kg_nm"] / r["sea_eff_expected"]) ** 2))  # noqa: E731
    assert err(r_full) < err(r_ref)


def test_each_ship_independent_of_others(cr_bundle, snapshot, cr_results):
    some = snapshot["imo"].drop_duplicates().sample(15, random_state=1)
    alone = pd.concat([cr_bundle.run(snapshot[snapshot["imo"] == i]) for i in some], ignore_index=True)
    full = cr_results[cr_results["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(alone.sort_values(["imo", "year"]).reset_index(drop=True), full, rtol=0, atol=1e-9)


def test_no_future_leak(cr_bundle, snapshot, cr_results):
    r = cr_bundle.run(snapshot[snapshot["year"] <= 2022])
    full = cr_results[cr_results["year"] <= 2022].reset_index(drop=True)
    pd.testing.assert_frame_equal(r.reset_index(drop=True), full, rtol=0, atol=1e-9)


def test_position_shrinks_toward_zero_with_few_years(cr_results):
    """같은 배라도 보고 연수가 적으면 선종 중간 쪽으로 더 줄어든다 (k 가 작음)."""
    first = cr_results[cr_results["position_n_years"] == 1]["position_z"].abs()
    later = cr_results[cr_results["position_n_years"] >= 5]["position_z"].abs()
    assert first.std() < later.std()


def test_cause_se_and_coefficient_table(snapshot, cr_cfg):
    k = next(i for i, s in enumerate(cr_cfg["stages"]) if s["use"].endswith("CommonResidualBaseline"))
    part = ModelBundle.train(snapshot, cr_cfg, until_stage=k + 1)
    work = part.run(snapshot)                                   # 기준 모델까지의 중간 표 (year_eff·size_bin 포함)
    stage = part.stages[k]
    se = stage.cause_se(work)
    assert len(se) == len(work) and (se.to_numpy() >= 0).all()
    assert {"se_size", "se_speed_pattern"} <= set(se.columns)
    tab = stage.coefficient_table()
    assert {"ship_type", "var", "coef", "se", "t"} <= set(tab.columns)
    assert tab["se"].gt(0).all()


def test_features_override_like_linear_baseline():
    """evaluation 은 features 를 덮어써서 '크기만' 기준을 만든다 → 같은 인자를 받아야 한다."""
    s = CommonResidualBaseline(features={"ln_dwt": "size"})
    assert s.groups == {"size": ["ln_dwt"]}
    with pytest.raises(ValueError):
        CommonResidualBaseline(features={"ln_dwt": "unexplained"})


# ───────────────────── 공통잔차 신판 (형식 1.0): 내빙 둘, 설계 종류, 선종 간 공유, 크기 열 ─────────────────────
from models.common.common_residual import pool_slopes  # noqa: E402
from models.common.peer import PeerGroup  # noqa: E402


def test_ice_split_and_design_tokens():
    s = CommonResidualBaseline()
    s.design_ref = {("tanker", "EEDI"): 2.0, ("tanker", "EIV"): 1.0}
    df = pd.DataFrame({
        "ship_type": ["tanker"] * 6, "ice_class": ["IA", "PC3", "IB", "IC", None, "IA Super"],
        "eedi_kind": ["EEDI", "EEXI", "EIV", None, "EEDI", "EEDI"], "eedi": [np.e**3, 5.0, np.e**1.5, 4.0, np.nan, 0.0],
    })
    assert s._raw(df, "ice_hi").tolist() == [1, 1, 0, 0, 0, 1]
    assert s._raw(df, "ice_lo").tolist() == [0, 0, 1, 1, 0, 0]
    assert s._raw(df, "design_EEDI").tolist() == [1, 0, 0, 0, 1, 1]
    assert s._raw(df, "design_EEXI").tolist() == [0, 1, 0, 0, 0, 0]
    # 값이 없거나 0 이하이거나 종류가 없으면 "없음" 표시, 설계 차이는 0
    assert s._raw(df, "design_none").tolist() == [0, 0, 0, 1, 1, 1]
    eff = s._raw(df, "design_eff").tolist()
    assert eff[0] == pytest.approx(1.0) and eff[2] == pytest.approx(0.5) and eff[3] == eff[4] == eff[5] == 0.0


def test_pool_slopes_pulls_uncertain_types_toward_the_mean():
    ts = ["a", "b", "c", "d"]
    coef = {"a": 0.10, "b": 0.12, "c": 0.11, "d": 0.60}               # d 는 멀리 있고
    var = {"a": 1e-4, "b": 1e-4, "c": 1e-4, "d": 0.04}                # 오차도 크다 → 많이 당겨져야 한다
    first = {t: (pd.Series({"x": coef[t]}), pd.DataFrame({"x": [var[t]]}, index=["x"])) for t in ts}
    out = pool_slopes(first, ["x"])
    assert 0.10 <= out["d"]["x"][0] < 0.20                             # 0.60 이 나머지 세 선종의 평균(약 0.11) 쪽으로 당겨진다
    assert abs(out["a"]["x"][0] - 0.10) < 0.02                         # 오차가 작은 선종은 거의 그대로
    assert pool_slopes({t: first[t] for t in ts[:2]}, ["x"]) == {"a": {}, "b": {}}      # 선종이 3개 미만이면 당기지 않음


def test_pooling_reduces_slope_spread_across_types(snapshot, cr_cfg):
    k = next(i for i, s in enumerate(cr_cfg["stages"]) if s["use"].endswith("CommonResidualBaseline"))

    def spread(pooling: bool) -> float:
        specs = [dict(s) for s in cr_cfg["stages"][: k + 1]]
        specs[k] = {**specs[k], "params": {"pooling": pooling}}
        st = ModelBundle.train(snapshot, cr_cfg, stage_specs=specs).stages[k]
        tab = st.coefficient_table()
        return float(tab[tab["var"] == "ln_sea_hours"].groupby("ship_type")["coef"].first().std())
    assert spread(True) <= spread(False) + 1e-12
    st = ModelBundle.train(snapshot, cr_cfg, until_stage=k + 1).stages[k]
    tab = st.coefficient_table()
    assert tab["pooled"].any() and not tab.loc[tab["var"].str.contains(r"\^2"), "pooled"].any()      # 2차항은 당기지 않는다


def test_peer_group_uses_size_col(snapshot):
    df = snapshot.assign(year_eff=snapshot["year"], sea_eff_kg_nm=snapshot["sea_eff_kg_nm"]).copy()
    df["gt"] = df["dwt"].rank()                                         # 다른 크기 열: 순위 (dwt 와 순서는 같지만 값이 다름)
    a = PeerGroup(size_col="gt")
    assert "gt" in a.requires and "dwt" not in a.requires
    out = a.fit(df, type("C", (), {"thresholds": {}})()).transform(df)  # 경계는 gt 에서 학습
    assert set(out["size_bin"]) <= {1, 2, 3, 4}
