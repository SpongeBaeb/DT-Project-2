"""다음 해 리스트 (models/forecast/lists.py, publish/lists.py): 규칙 경계, 학습 때 고정한 기준 p*, 순위·산출물."""
import numpy as np
import pandas as pd
import pytest

from models.base import FitContext
from models.forecast.lists import ListRule
from publish import lists as publish_lists

CTX = FitContext(cutoff_year=None, seed=0, thresholds={})


def frame(**cols):
    n = len(next(iter(cols.values())))
    base = {"year": [2025] * n, "cii_rating": ["B"] * n, "p_de_h1": [0.1] * n, "p_miss_h1": [0.5] * n}
    return pd.DataFrame({**base, **cols})


def test_target_boundary_and_priority_over_watch():
    train = frame(p_de_h1=[0.8, 0.79999, 0.9, 0.1], p_miss_h1=[0.9, 0.9, 0.1, 0.1], cii_rating=list("BBBB"))
    r = ListRule(de_cut=0.8).fit(train, CTX)
    got = r.transform(train)["list_h1"].tolist()
    assert got[0] == "target"                        # 정확히 0.8 은 타깃, 타깃이면 관찰 조건이 맞아도 타깃
    assert got[2] == "target" and got[3] == ""


def test_watch_needs_a_good_rating_and_a_high_miss_probability():
    train = frame(p_miss_h1=np.linspace(0, 1, 101)[:100].tolist() + [1.0] * 0, cii_rating=["B"] * 100, p_de_h1=[0.1] * 100)
    r = ListRule(watch_quantile=0.75).fit(train, CTX)
    assert r.p_star == pytest.approx(np.quantile(train["p_miss_h1"], 0.75))
    d = frame(p_miss_h1=[r.p_star, r.p_star - 1e-6, r.p_star, r.p_star, r.p_star], cii_rating=["A", "A", "C", "D", "E"])
    assert r.transform(d)["list_h1"].tolist() == ["watch", "", "watch", "", ""]      # p* 이상 · A~C 만. D·E 는 관찰이 아님


def test_p_star_uses_only_the_last_training_year():
    old = frame(year=[2023] * 50, p_miss_h1=[0.99] * 50)
    new = frame(year=[2025] * 50, p_miss_h1=np.linspace(0, 0.5, 50).tolist())
    r = ListRule().fit(pd.concat([old, new], ignore_index=True), CTX)
    assert r.base_year == 2025 and r.p_star == pytest.approx(np.quantile(new["p_miss_h1"], 0.75)) and r.p_star < 0.5


def test_missing_probabilities_give_an_empty_list():
    train = frame(p_miss_h1=[0.1, 0.9, 0.5, 0.7])
    r = ListRule().fit(train, CTX)
    d = frame(p_de_h1=[np.nan, np.nan], p_miss_h1=[np.nan, np.nan])
    assert r.transform(d)["list_h1"].tolist() == ["", ""]


def test_needs_miss_probabilities_at_fit_time():
    with pytest.raises(ValueError, match="p_miss_h1"):
        ListRule().fit(frame(p_miss_h1=[np.nan, np.nan]), CTX)


def test_describe_records_the_frozen_threshold():
    d = ListRule().fit(frame(p_miss_h1=[0.2, 0.4, 0.6, 0.8]), CTX).describe()["detail"]
    assert d["base_year"] == 2025 and d["watch_ratings"] == ["A", "B", "C"] and 0.6 < d["p_star"] < 0.8


# ───────────────────────── 산출물: 순위 ─────────────────────────
def _results():
    return pd.DataFrame({
        "imo": [5, 1, 3, 2, 4, 6], "year": [2025] * 6, "ship_type": ["tanker"] * 6,        # 실제 결과 표처럼 ship_type 이 이미 있다 (스냅샷과 겹침 방지)
        "list_h1": ["target", "target", "watch", "target", "", "watch"], "p_de_h1": [0.9, 0.95, 0.3, 0.9, 0.1, 0.4],
        "p_de_h2": [0.5] * 6, "p_de_h3": [0.6] * 6, "p_miss_h1": [0.5, 0.5, 0.8, 0.5, 0.2, 0.9], "fct_h1_p50": [440.0] * 6,
    })


def _snapshot():
    return pd.DataFrame({"imo": range(1, 7), "year": 2025, "name": list("ABCDEF"), "ship_type": "tanker", "company": "X", "cii_rating": list("CCBBAB"), "co2_per_nm_kg": [400.0] * 6})


def test_rank_is_by_de_probability_within_each_list_with_imo_tiebreak():
    t, year = publish_lists.build_list(_results(), _snapshot())
    assert year == 2025 and set(t["리스트"]) == {"영업 타깃", "관찰"} and len(t) == 5           # 리스트에 없는 배는 빠진다
    tg = t[t["리스트"] == "영업 타깃"]
    assert tg["IMO"].tolist() == [1, 2, 5] and tg["순위"].tolist() == [1, 2, 3]               # 0.95, 0.90(imo 2 먼저), 0.90(imo 5)
    assert t[t["리스트"] == "관찰"]["IMO"].tolist() == [6, 3] or t[t["리스트"] == "관찰"].sort_values("순위")["IMO"].tolist() == [6, 3]
    assert t["리스트"].iloc[0] == "영업 타깃"                                                   # 타깃이 먼저
    assert t.loc[t["IMO"] == 1, "2026년 거리당 CO₂ 변화(대표값, %)"].iloc[0] == pytest.approx(10.0)


def test_build_list_requires_the_list_column():
    with pytest.raises(ValueError, match="ListRule"):
        publish_lists.build_list(_results().drop(columns="list_h1"), _snapshot())


def test_run_writes_files_and_a_summary_with_the_threshold(tmp_path):
    meta = {"stages": [{"use": "x"}, {"use": "y", "detail": {"base_year": 2025, "p_star": 0.715, "de_cut": 0.8, "watch_quantile": 0.75, "watch_ratings": ["A", "B", "C"]}}]}
    t = publish_lists.run(_results(), _snapshot(), tmp_path, meta)
    assert (tmp_path / "리스트_2026.csv").exists() and (tmp_path / "리스트_2026.parquet").exists()
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "0.715" in text and "영업 타깃 3척, 관찰 2척" in text and "신뢰 등급" in text
    assert len(t) == 5
