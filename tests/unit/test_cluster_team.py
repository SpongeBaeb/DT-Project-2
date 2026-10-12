"""팀 군집 Stage (models/cluster/team.py): 변수 계산, 유형 번호 규칙, 소속 확률, 이상 운항, 한 척 = 전체·미래 누수 없음.

팀 노트북 결과 숫자와의 대조는 experiments/A-3_cluster/verify_cluster.py (실제 데이터, 수동 실행).
"""
import numpy as np
import pandas as pd
import pytest

from models.base import FitContext
from models.cluster.team import OpsAnomaly, TeamTypes, apply_rel, rel, soft_membership, window_median

CTX = FitContext(cutoff_year=None, seed=0, thresholds={})


# ───────────────────────── 변수 ─────────────────────────
def test_window_median_uses_only_the_last_available_years_up_to_now():
    d = pd.DataFrame({"imo": [1] * 5, "year": [2021, 2022, 2023, 2024, 2025], "v": [10.0, 20.0, 30.0, 40.0, 100.0]})
    assert window_median(d, "v", 3).tolist() == [10.0, 15.0, 20.0, 30.0, 40.0]            # 2025 → 2023~2025 의 중앙값 40
    gap = d[d["year"] != 2023].reset_index(drop=True)                                         # 2023 보고 없음: 있는 해만으로 중앙값
    assert window_median(gap, "v", 3).tolist()[-2:] == [30.0, 70.0]                           # 2024 → {20,40}=30, 2025 → {40,100}=70
    d2 = d.assign(imo=[1, 1, 1, 2, 2])
    assert window_median(d2, "v", 3)[3] == 40.0                                               # 다른 배 값은 섞이지 않는다


def test_relative_value_clips_and_handles_zero_spread():
    v = pd.Series(np.r_[np.random.default_rng(0).normal(0, 1, 500), [50.0]])
    med, spread = rel(v)
    r = apply_rel(v.to_numpy(), med, spread)
    assert r.max() == 4 and abs(np.median(r)) < 0.05
    assert apply_rel(np.array([1.0, 2.0]), 1.0, 0.0).tolist() == [0.0, 0.0]                   # 퍼짐이 0 이면 0


def test_soft_membership_is_a_distribution_peaking_at_the_nearest_center():
    c = np.array([[0.0, 0.0], [5.0, 0.0], [0.0, 5.0]])
    Z = np.array([[0.2, 0.1], [4.8, 0.2], [0.1, 4.9]])
    near, P = soft_membership(Z, c, 1.0)
    assert near.tolist() == [0, 1, 2] and np.allclose(P.sum(axis=1), 1) and (P.argmax(axis=1) == near).all() and P.max(axis=1).min() > 0.99


# ───────────────────────── 두 축 유형 ─────────────────────────
def fleet(n=200, seed=0):
    """뚜렷한 세 무리: 노출도(역내 / 정기 / 비정기) × 프로파일(고효율·젊음 / 일반 / 고선령). 한 척 한 줄, 2025년 보고."""
    rng = np.random.default_rng(seed)
    rows = []
    imo = 1
    for expo, (eu, hours) in {"역내": (0.8, 2000), "정기": (0.05, 5000), "비정기": (0.05, 300)}.items():
        for prof, (age, delta) in {"고효율": (5, -0.4), "일반": (14, 0.0), "고선령": (30, 0.0)}.items():
            for _ in range(n // 3):
                dwt = float(rng.uniform(30_000, 150_000))
                rows.append({"imo": imo, "year": 2025, "year_eff": 2025, "ship_type": "tanker", "eu_share": eu + rng.normal(0, 0.02),
                             "sea_hours": hours * np.exp(rng.normal(0, 0.05)), "age": age + rng.normal(0, 1), "dwt": dwt, "gt": dwt * 0.6,
                             "eedi": 20 * dwt ** -0.2 * np.exp(delta + rng.normal(0, 0.03)), "eedi_kind": "EEDI", "co2_parts_bad": False,
                             "_e": expo, "_p": prof})
                imo += 1
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def typed():
    d = fleet()
    st = TeamTypes().fit(d, CTX)
    return d, st, st.transform(d)


def test_type_numbers_follow_the_team_rules(typed):
    d, st, out = typed
    e = out["type_exposure"].groupby(d["_e"]).agg(lambda s: s.mode().iloc[0])
    assert e.to_dict() == {"역내": 1, "정기": 2, "비정기": 3}                                 # 역내 비중 최고=1, 남은 둘 중 해상 시간 긴 쪽=2
    p = out["type_age_design"].groupby(d["_p"]).agg(lambda s: s.mode().iloc[0])
    assert p.to_dict() == {"고효율": 1, "일반": 2, "고선령": 3}                               # 설계 효율 가장 좋음=1, 남은 둘 중 선령 높은 쪽=3
    assert out["type_exposure_prob"].between(0, 1).all() and out["type_age_design_prob"].between(0, 1).all()
    assert (out["type_exposure_prob"] > 0.9).mean() > 0.95                                    # 뚜렷한 무리는 소속 확률이 높다


def test_missing_design_value_means_no_profile_but_keeps_the_exposure_type(typed):
    d, st, _ = typed
    out = st.transform(d.head(6).assign(eedi=np.nan))
    assert out["type_age_design"].isna().all() and out["type_age_design_prob"].isna().all() and out["type_exposure"].notna().all()
    assert st.transform(d.head(6).assign(eedi_kind=None))["type_age_design"].isna().all()    # 지표 종류가 없어도 마찬가지


def test_one_ship_equals_full_and_no_future_leak():
    d = fleet(60)
    hist = pd.concat([d.assign(year=y, year_eff=2025, sea_hours=d["sea_hours"] * (1 + 0.2 * (2025 - y))) for y in (2023, 2024, 2025)], ignore_index=True)
    st = TeamTypes().fit(hist, CTX)
    full = st.transform(hist)
    one = hist[hist["imo"] == 7]
    pd.testing.assert_frame_equal(st.transform(one), full.loc[one.index], rtol=0, atol=1e-12)
    past = hist[hist["year"] <= 2024]
    pd.testing.assert_frame_equal(st.transform(past), full.loc[past.index], rtol=0, atol=1e-12)           # 미래 연도를 지워도 같다


def test_unknown_ship_type_gives_no_profile_without_failing(typed):
    d, st, _ = typed
    assert st.transform(d.head(4).assign(ship_type="submarine"))["type_age_design"].isna().all()


def test_describe_lists_centers_by_type_name(typed):
    det = typed[1].describe()["detail"]
    assert set(det["exposure_centers"]) == {"역내 운항선", "정기 기항선", "비정기 기항선"} and set(det["profile_centers"]) == {"고효율형", "일반형", "고선령형"}


# ───────────────────────── 이상 운항 ─────────────────────────
def ops_frame(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    co2 = rng.uniform(5000, 20000, n)
    return pd.DataFrame({
        "imo": np.arange(n), "year": 2025, "year_eff": 2025, "ship_type": "tanker", "eu_share": rng.beta(2, 8, n), "co2_t": co2,
        "co2_from_eu_t": co2 * rng.beta(2, 8, n) * 0.5, "co2_to_eu_t": co2 * rng.beta(2, 8, n) * 0.5, "berth_share": rng.beta(1.5, 20, n),
        "sea_hours": rng.lognormal(7.5, 0.5, n), "avg_speed_kn": rng.normal(12, 1.2, n).clip(5), "co2_parts_bad": False})


def test_extreme_operations_are_flagged_and_about_top_share_overall():
    d = ops_frame()
    d.loc[:9, "berth_share"] = np.linspace(0.90, 0.99, 10)                                    # 정박 비중이 터무니없이 큰 10척 (0.5% 미만: 군집 중심을 만들 만큼 많지 않다)
    flag = OpsAnomaly().fit(d, CTX).transform(d)["ops_outlier"]
    assert flag[:10].all() and abs(flag.mean() - 0.025) < 0.002
    assert flag.dtype == bool


def test_ops_outlier_never_fires_when_the_metrics_cannot_be_trusted_or_type_unknown():
    d = ops_frame()
    op = OpsAnomaly().fit(d, CTX)
    assert not op.transform(d.head(50).assign(co2_parts_bad=True, berth_share=0.99))["ops_outlier"].any()
    assert not op.transform(d.head(50).assign(ship_type="submarine", berth_share=0.99))["ops_outlier"].any()


def test_ops_outlier_one_ship_equals_full():
    d = ops_frame(1500)
    op = OpsAnomaly().fit(d, CTX)
    full = op.transform(d)
    for i in (3, 77, 900):
        pd.testing.assert_frame_equal(op.transform(d[d["imo"] == i]), full.loc[d["imo"] == i])


def test_ops_threshold_is_frozen_at_fit_time():
    """기준 거리는 학습 때 정한 값이라, 다른 배가 섞인 표에 넣어도 한 배의 판정은 변하지 않는다."""
    d = ops_frame(1500)
    op = OpsAnomaly().fit(d, CTX)
    extra = pd.concat([d, ops_frame(500, seed=9).assign(imo=lambda x: x["imo"] + 10_000, berth_share=0.9)], ignore_index=True)
    assert op.transform(extra).loc[: len(d) - 1, "ops_outlier"].tolist() == op.transform(d)["ops_outlier"].tolist()
