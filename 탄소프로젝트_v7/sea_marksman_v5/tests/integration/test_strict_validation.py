"""엄격한 시간 분할 검증 (evaluation/strict.py): 지표 계산, 미래 정보 차단, 시험 구성.

팀 type_eval_v4.csv 와의 수치 대조는 experiments/A-4_trust_inputs/reproduce_type_eval.py (구판 데이터, 수동 실행).
"""
import numpy as np
import pandas as pd
import pytest

from evaluation.strict import TESTS, overall_table, strict_predictions, type_table

SMALL = {1: (2022,), 2: (2021,)}


@pytest.fixture(scope="module")
def sp(snapshot):
    return strict_predictions(snapshot, "sea_eff_kg_nm", seed=0, tests=SMALL)


def test_default_tests_match_the_team_design():
    assert TESTS == {1: (2023, 2024), 2: (2022, 2023), 3: (2022,)}


def test_predictions_have_one_row_per_ship_and_test(sp, snapshot):
    assert set(sp["h"]) == {1, 2} and set(sp["t"]) == {2022, 2021}
    assert not sp.duplicated(["imo", "h", "t"]).any()
    assert (sp["target_year"] == sp["t"] + sp["h"]).all()
    assert np.allclose(np.log(sp["level_target"] / sp["level_t"]), sp["delta"])               # 실제 변화 = ln(목표 ÷ 출발)
    assert (sp[["q5", "q10", "q25", "q50", "q75", "q90", "q95"]].diff(axis=1).iloc[:, 1:] >= -1e-12).all().all()    # 분위는 오름차순
    assert sp["level"].eq("sea_eff_kg_nm").all()


def test_a_prediction_never_uses_data_after_the_start_year(snapshot, sp):
    """출발 연도 t 의 예측은 목표 연도 ≤ t 인 정보만 쓴다: 목표 연도 t+h 이후의 행을 지워도 (실제 값만 있으면) 대표값이 같다."""
    cut = snapshot[snapshot["year"] <= 2023]                                                   # 출발 2022 + 1년 = 2023 까지만 남김
    again = strict_predictions(cut, "sea_eff_kg_nm", seed=0, tests={1: (2022,)})
    a = sp[(sp["h"] == 1) & (sp["t"] == 2022)].set_index("imo")
    b = again.set_index("imo")
    common = a.index.intersection(b.index)
    assert len(common) > 100
    pd.testing.assert_series_equal(a.loc[common, "m"], b.loc[common, "m"], rtol=0, atol=1e-9)
    pd.testing.assert_series_equal(a.loc[common, "q90"], b.loc[common, "q90"], rtol=0, atol=1e-9)


def test_retrain_option_changes_predictions_but_not_the_pairs(snapshot, sp):
    r = strict_predictions(snapshot, "sea_eff_kg_nm", seed=0, tests={1: (2022,)}, retrain=True)
    a = sp[(sp["h"] == 1) & (sp["t"] == 2022)].set_index("imo")
    b = r.set_index("imo")
    assert a.index.equals(b.index) and np.allclose(a["delta"], b["delta"])
    assert not np.allclose(a["m"], b["m"])                                                     # 보정 연도까지 학습하면 대표값이 달라진다


def hand_preds():
    """손으로 계산할 수 있는 작은 예측 표 (한 선종, h=1, 두 시험 연도, 쌍 10개)."""
    n = 10
    return pd.DataFrame({
        "ship_type": "tanker", "h": 1, "t": [2023] * 5 + [2024] * 5, "target_year": [2024] * 5 + [2025] * 5,
        "delta": [0.1, -0.1, 0.2, 0.0, 0.3, -0.2, 0.1, 0.0, 0.1, 0.4], "m": [0.0] * n,
        "q10": [-0.15] * n, "q90": [0.15] * n, "q25": [-0.05] * n, "q75": [0.05] * n, "pred_linear": [0.05] * n,
        "thr_de": np.linspace(-0.5, 0.4, n), "p_de": np.linspace(0.1, 0.9, n), "p_de_nochange": np.linspace(0.1, 0.9, n),
        "de_target": [0, 0, 1, 0, 0, 0, 1, 1, 1, 1.0],
    })


def test_type_table_metrics_by_hand():
    t = type_table(hand_preds()).iloc[0]
    d = hand_preds()
    assert t["쌍"] == 10 and t["연평균 척수"] == 5
    assert t["MAE 변화 없음"] == pytest.approx(d["delta"].abs().mean()) and t["MAE v4"] == pytest.approx(d["delta"].abs().mean())      # m=0
    assert t["MAE 선형"] == pytest.approx((d["delta"] - 0.05).abs().mean())
    assert t["치우침 2024"] == pytest.approx(d["delta"][:5].mean()) and t["치우침 2025"] == pytest.approx(d["delta"][5:].mean())       # 목표 연도별
    assert t["구간 포함률%"] == pytest.approx(60.0)                                            # |Δ| ≤ 0.15 인 쌍: 0.1, −0.1, 0, 0.1, 0, 0.1 = 6개
    assert t["변화 없음 대비%"] == pytest.approx(0.0)
    assert t["실제 D·E%"] == pytest.approx(50.0) and t["D·E 예측−실제 %p"] == pytest.approx((0.5 - 0.5) * 100)
    # 상위 10% = 1개 (10쌍 × 0.1): 규칙 점수 −thr 최고(= 마지막이 아닌 첫 행) → de_target[0]=0, v4 점수 p_de 최고(마지막) → 1
    assert t["상위10% 규칙"] == pytest.approx(0.0) and t["상위10% v4"] == pytest.approx(100.0) and t["상위10% 차이 %p"] == pytest.approx(100.0)


def test_top_ten_percent_count_is_rounded_like_the_team():
    """94쌍 → 9개(반올림), 팀 type_eval_v4.csv 의 다른 선종·기간과 같은 방식."""
    d = pd.concat([hand_preds()] * 10, ignore_index=True).head(94)
    d["de_target"], d["p_de"], d["thr_de"] = 1.0, np.linspace(0, 1, 94), -np.linspace(0, 1, 94)
    t = type_table(d).iloc[0]
    assert t["상위10% v4"] == 100.0 and t["쌍"] == 94


def test_overall_table_has_the_team_metric_names():
    o = overall_table(hand_preds()).iloc[0]
    for c in ("MAE v4", "MAE 선형", "MAE 변화없음", "치우침 v4", "80% 포함 v4", "50% 포함 v4", "D·E AUC v4", "D·E 예측−실제 %p", "Brier D·E"):
        assert c in o.index
    assert 0.5 < o["D·E AUC v4"] <= 1.0
