"""군집 Stage(TeamTypes, OpsAnomaly)를 번들에 끼웠을 때의 약속: 계약, 한 척 = 전체, 미래 누수 없음, 저장·불러오기.

기본 설정은 그대로 두고 합성 표본에서 임시 부품 TertileTypes 자리에 이 부품 둘을 끼워 확인한다.
수치 재현은 experiments/A-3_cluster/verify_cluster.py (실제 데이터, 수동 실행).
"""
import copy

import numpy as np
import pandas as pd
import pytest

from contracts.tables import RESULT_TABLE
from models.bundle import ModelBundle

STAGES = [
    {"use": "models.cluster.team:TeamTypes", "params": {"k": 3, "n_init": 3}},
    {"use": "models.cluster.team:OpsAnomaly", "params": {"k": 3, "n_init": 3}},
]


@pytest.fixture(scope="module")
def csnap(snapshot):
    """합성 표본에 출항·입항 EU 비중 열을 붙인다 (표본 파일에는 없음)."""
    rng = np.random.default_rng(0)
    n = len(snapshot)
    eedi = 20 * snapshot["dwt"] ** -0.2 * np.exp(rng.normal(0, 0.2, n))                 # 설계 효율 값도 붙인다 (선령·설계 축 확인용)
    return snapshot.assign(co2_from_eu_t=snapshot["co2_t"] * rng.beta(2, 8, n) * 0.5, co2_to_eu_t=snapshot["co2_t"] * rng.beta(2, 8, n) * 0.5,
                           eedi=eedi, eedi_kind="EEDI")


@pytest.fixture(scope="module")
def ccfg(cfg):
    c = copy.deepcopy(cfg)
    c["stages"] = [s for s in c["stages"] if not s["use"].endswith("TertileTypes")] + STAGES
    return c


@pytest.fixture(scope="module")
def cbundle(csnap, ccfg):
    return ModelBundle.train(csnap, ccfg)


@pytest.fixture(scope="module")
def cres(cbundle, csnap):
    return cbundle.run(csnap)


def test_meets_contract_and_fills_the_type_columns(cres, csnap):
    RESULT_TABLE.validate(cres, extra="forbid")
    assert len(cres) == len(csnap)
    assert cres["type_exposure"].isin([1, 2, 3]).all() and set(cres["type_exposure"].dropna().unique()) <= {1, 2, 3}
    assert cres["type_exposure_prob"].between(0, 1).all()
    assert cres["type_age_design"].dropna().isin([1, 2, 3]).all()
    assert cres["ops_outlier"].dtype == bool and 0 < cres["ops_outlier"].mean() < 0.06


def test_each_ship_independent_of_others(cbundle, csnap, cres):
    some = csnap["imo"].drop_duplicates().sample(12, random_state=4)
    alone = pd.concat([cbundle.run(csnap[csnap["imo"] == i]) for i in some], ignore_index=True).sort_values(["imo", "year"]).reset_index(drop=True)
    full = cres[cres["imo"].isin(some)].sort_values(["imo", "year"]).reset_index(drop=True)
    cols = ["imo", "year", "type_exposure", "type_age_design", "type_exposure_prob", "type_age_design_prob", "ops_outlier"]
    pd.testing.assert_frame_equal(alone[cols], full[cols], rtol=0, atol=1e-9)


def test_no_future_leak(cbundle, csnap, cres):
    past = cbundle.run(csnap[csnap["year"] <= 2022])
    cols = ["imo", "year", "type_exposure", "type_age_design", "type_exposure_prob", "type_age_design_prob", "ops_outlier"]
    pd.testing.assert_frame_equal(past[cols].reset_index(drop=True), cres[cres["year"] <= 2022][cols].reset_index(drop=True), rtol=0, atol=1e-9)


def test_save_load_roundtrip(cbundle, csnap, cres, tmp_path):
    cbundle.save(tmp_path)
    again = ModelBundle.load(tmp_path).run(csnap)
    pd.testing.assert_frame_equal(again, cres, rtol=0, atol=0)
    detail = {s["use"]: s.get("detail") for s in cbundle.meta["stages"]}
    assert "exposure_centers" in detail["models.cluster.team:TeamTypes"] and "types" in detail["models.cluster.team:OpsAnomaly"]


def test_the_stub_still_works_in_the_default_config(results):
    """기본 설정(임시 부품)은 그대로 — 새 선택 열(소속 확률)은 빈칸."""
    assert results["type_exposure_prob"].isna().all() and results["type_exposure"].notna().all()


def test_missing_design_values_skip_the_profile_axis_instead_of_failing(snapshot, ccfg):
    """표본처럼 설계 효율 값이 아예 없는 선단: 노출도 유형은 만들고 선령·설계 유형은 빈칸."""
    snap = snapshot.assign(co2_from_eu_t=snapshot["co2_t"] * 0.1, co2_to_eu_t=snapshot["co2_t"] * 0.1)
    r = ModelBundle.train(snap, ccfg).run(snap)
    assert r["type_exposure"].notna().all() and r["type_age_design"].isna().all() and r["type_age_design_prob"].isna().all()
    RESULT_TABLE.validate(r, extra="forbid")
