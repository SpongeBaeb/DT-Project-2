"""비용 계산 (cost/model.py, cost/run.py): 분해의 합 = 변화, 연료 단가 규칙, 탄소 비용 식, 표 3 정의, 입력 조립.

팀 표와의 수치 대조는 experiments/A-2_cost/verify_cost.py (수동 실행).
"""
import itertools

import numpy as np
import pandas as pd
import pytest

from contracts.tables import TOTAL_FORECAST_COLS
from cost import model, run

S, META, RAW = model.load_settings()
PRICES = model.load_prices(RAW["prices_file"])


def ships(**over):
    d = pd.DataFrame({
        "imo": [1, 2, 3, 4, 5], "선박명": list("ABCDE"), "선종": "유조선",
        "fuel_group": ["석유계", "석유계", "LNG 계열", "LPG 추정", "기타 대체연료"],
        "fuel_t": [5000.0, 3000.0, 4000.0, 1000.0, 800.0], "co2_per_fuel": [3.114, 3.206, 2.75, 3.0, 3.15],
        "ets_co2_t": [9000.0, 6000.0, 8000.0, 0.0, 1500.0], "ets_co2eq_t": [9100.0, 6050.0, 8300.0, 0.0, 1520.0],
        "distance_nm": [30000.0] * 5,
    })
    return d.assign(**over)


def ratios(r=1.0):
    return {(y, k): np.full(5, r) for y in S["years"] for k in model.KINDS}


def test_split_product_parts_sum_to_the_change_for_any_order():
    rng = np.random.default_rng(0)
    f0, f1 = [rng.uniform(0.5, 2, 6) for _ in range(3)], [rng.uniform(0.5, 2, 6) for _ in range(3)]
    change = np.prod(f1, axis=0) - np.prod(f0, axis=0)
    np.testing.assert_allclose(np.sum(model.split_product(f0, f1), axis=0), change, atol=1e-12)
    for order in itertools.permutations(range(3)):
        np.testing.assert_allclose(np.sum(model.split_product(f0, f1, order), axis=0), change, atol=1e-12)


def test_split_product_with_one_changing_factor_gives_it_everything():
    f0, f1 = [np.array([2.0]), np.array([3.0])], [np.array([5.0]), np.array([3.0])]
    a, b = model.split_product(f0, f1)
    assert a[0] == pytest.approx(9.0) and b[0] == pytest.approx(0.0)


@pytest.mark.parametrize("group, cpf, want", [
    ("석유계", 3.114, 704.1), ("석유계", 3.206, 1429.4), ("석유계", 3.1785, (704.1 + 1429.4) / 2),     # 잔사유(저유황유) ↔ 경유 혼합
    ("석유계", 3.0, 704.1),                                                                           # 잔사유 계수 아래는 잔사유 100%
    ("LNG 계열", 2.75, 1484.3), ("LNG 계열", 3.151, 704.1), ("기타 대체연료", 3.15, 704.1),            # LNG ↔ 잔사유, 기타는 석유계 가격으로 근사
])
def test_fuel_unit_price_rules_scenario_base(group, cpf, want):
    d = pd.DataFrame({"fuel_group": [group], "co2_per_fuel": [cpf]})
    assert model.fuel_unit_price(d, PRICES, "기준", "A", S).iloc[0] == pytest.approx(want)


def test_lpg_has_no_fuel_price():
    d = pd.DataFrame({"fuel_group": ["LPG 추정"], "co2_per_fuel": [3.0]})
    assert np.isnan(model.fuel_unit_price(d, PRICES, "기준", "A", S).iloc[0])


def test_carbon_cost_formula_and_gas_scope():
    d = ships()
    fxe, eua = PRICES.loc["환율 EUR", "기준"], PRICES.loc["배출권(EUA)", "기준"]
    q25 = np.prod(model.carbon_factors(d, np.ones(5), 2025, 74.0, fxe, S), axis=0)
    assert q25[0] == pytest.approx(9000 * 0.70 * 74.0 * fxe)                         # 2025: CO₂만, 제출 70%
    q26 = np.prod(model.carbon_factors(d, np.ones(5), 2026, eua, fxe, S), axis=0)
    assert q26[0] == pytest.approx(9000 * (9100 / 9000) * 1.0 * eua * fxe)           # 2026~: CH₄·N₂O 포함(eq ÷ co2), 제출 100%
    assert q26[3] == 0.0                                                             # ETS 대상 배출이 0 이면 탄소 비용 0


def test_tables_have_the_documented_shape_and_identities():
    t1, t2 = model.build(ships(), ratios(0.95), PRICES, S)
    n = 5 * len(S["years"]) * len(model.SCENARIOS)
    assert len(t1) == len(t2) == n
    assert t2["검산_합빼기총변화"].abs().max() < 1e-9                                  # 효율 + 규제 + 가격 = 총 변화
    one = t1[(t1["imo"] == 1) & (t1["연도"] == 2026) & (t1["시나리오"] == "기준")].iloc[0]
    assert one["연료량_t_대표"] == pytest.approx(5000 * 0.95)
    assert one["총비용_대표"] == pytest.approx(one["연료비_대표"] + one["탄소비용_대표"])
    assert one["연료비_비중_pct"] + one["탄소비용_비중_pct"] == pytest.approx(100.0)


def test_base_year_cost_does_not_depend_on_scenario_or_year():
    t1, _ = model.build(ships(), ratios(1.1), PRICES, S)
    assert t1.groupby("imo")["총비용_2025"].nunique(dropna=False).le(1).all()


def test_lpg_ship_has_carbon_cost_but_no_fuel_or_total_cost():
    t1, _ = model.build(ships(), ratios(1.0), PRICES, S)
    lpg = t1[t1["imo"] == 4]
    assert lpg["연료비_대표"].isna().all() and lpg["총비용_대표"].isna().all()
    assert (lpg["표시"] == "연료비 없음(LPG 가격 미정)").all()


def test_no_change_in_efficiency_leaves_only_regulation_and_price_effects():
    _, t2 = model.build(ships(), ratios(1.0), PRICES, S)
    assert t2["효율몫_대표"].dropna().abs().max() < 1e-9
    assert (t2.loc[t2["시나리오"] == "낮음", "가격몫_연료"].dropna().abs() < 1e-9).all()      # 낮음 시나리오의 연료 가격은 2025 와 같음


def test_peer_baseline_replaces_only_the_sailing_part():
    d = ships()
    sea_peer, berth = pd.Series([300.0] * 5), pd.Series([20.0] * 5)
    peer, note = model.peer_fuel_per_nm(d, sea_peer, berth)
    np.testing.assert_allclose(peer, 320.0 / d["co2_per_fuel"])
    assert note.eq("공통잔차 동급 중간(해상) + 이 배의 정박").all()
    assert model.peer_fuel_per_nm(d, pd.Series([np.nan] * 5), berth)[1].eq("기준값 없음").all()


def test_table3_is_zero_when_the_ship_is_exactly_at_peer():
    d = ships()
    t1, _ = model.build(d, ratios(1.0), PRICES, S)
    actual = d["fuel_t"] * 1000 / d["distance_nm"]
    t3 = model.build_t3(d, t1, actual, pd.Series("테스트", index=d.index), S)
    assert t3["동급대비_차이"].dropna().abs().max() < 1e-6 and t3["동급대비_차이_pct"].dropna().abs().max() < 1e-6


def _frames():
    d = ships()
    snap = d.assign(year=2025, name=d["선박명"], ship_type="tanker").drop(columns=["선박명", "선종"])
    snap["co2_per_nm_kg"] = 400.0
    snap["sea_eff_kg_nm"] = 380.0
    res = snap[["imo", "year"]].assign(sea_eff_peer_median=360.0)
    for h in (1, 2, 3):
        for q, f in ((10, 0.9), (50, 1.0), (90, 1.1)):
            res[f"fct_h{h}_p{q}"] = 400.0 * f
    return snap, res


def test_prepare_inputs_builds_ratios_from_the_total_efficiency_forecast():
    snap, res = _frames()
    d, r = run.prepare_inputs(snap, res, S)
    assert len(d) == 5 and d["선종"].eq("유조선").all()
    assert r[(2026, "대표")] == pytest.approx(np.ones(5)) and r[(2026, "하한")] == pytest.approx(np.full(5, 0.9)) and r[(2028, "상한")] == pytest.approx(np.full(5, 1.1))


def test_missing_total_forecast_is_reported_clearly():
    snap, res = _frames()
    with pytest.raises(ValueError, match="fct_h"):
        run.prepare_inputs(snap, res.drop(columns=TOTAL_FORECAST_COLS), S)


def test_run_writes_tables_and_a_summary_listing_unsettled_settings(tmp_path):
    snap, res = _frames()
    tables = run.run(snap, res, tmp_path)
    assert set(tables) == {"표1_배별_비용", "표2_변화_분해", "표3_동급_대비"}
    for name in tables:
        assert (tmp_path / f"{name}.csv").exists() and (tmp_path / f"{name}.parquet").exists()
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "확정되지 않은 설정" in text and "lpg_price" in text and "oil_mix" in text and "decomp_rule" in text
    assert "fx_from_csv" in text and "ets_share" not in text.split("## 입력")[0]            # 확정 설정은 나열하지 않는다
