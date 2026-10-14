"""유지 확률 Stage (models/forecast/persist.py): 라벨, 한 척 = 전체, 미래 정보 차단, 결과 표 연결."""
import copy

import numpy as np
import pandas as pd
import pytest

from models.base import FitContext
from models.bundle import ModelBundle
from models.forecast.persist import PersistProbability

SPEC = {"use": "models.forecast.persist:PersistProbability"}


@pytest.fixture(scope="module")
def work(snapshot, cfg):
    """앞 Stage(기준·잔차·정박·위치)만 학습해 돌린 중간 표 (persist 의 입력 열이 모두 있음)."""
    b = ModelBundle.train(snapshot, cfg, until_stage=4)
    return b.run(snapshot)


@pytest.fixture(scope="module")
def ctx(cfg):
    return FitContext(cutoff_year=None, seed=0, thresholds=cfg["thresholds"], config=cfg)


@pytest.fixture(scope="module")
def stage(work, ctx):
    return PersistProbability().fit(work.copy(), ctx)


def test_outputs_are_probabilities_with_reason_names(stage, work):
    out = stage.transform(work)
    assert list(out.columns) == ["persist_prob", "persist_up", "persist_down"] and out.index.equals(work.index)
    assert out["persist_prob"].between(0, 1).all() and out["persist_prob"].notna().all()
    names = set(out["persist_up"].dropna()) | set(out["persist_down"].dropna())
    assert names and names <= {"판정값 크기", "EU 해상 시간", "올해 같은 조건 대비 차이", "동급 대비 격차", "자기 과거 대비 변화", "보고 연수", "정박 배출"}


def test_label_pairs_need_a_report_in_the_next_calendar_year(stage, work):
    X, y = stage.pairs(work)
    d = work.set_index(["imo", "year"])["contrib_unexplained"]
    keys = work.loc[X.index, ["imo", "year"]]
    nxt = np.array([d.get((i, t + 1), np.nan) for i, t in zip(keys["imo"], keys["year"])])
    assert not np.isnan(nxt).any()                                                # 쌍에 들어온 행은 모두 다음 해 보고가 있다
    assert (y.to_numpy() == (nxt > np.log(1.10)).astype(float)).all()           # 라벨 = t+1년 잔차 > ln(1.10)
    assert len(y) < len(work)                                                     # 마지막 해와 한 해 건너뛴 쌍은 라벨이 없다


def test_one_ship_alone_gets_the_same_probability_as_the_full_table(stage, work):
    full = stage.transform(work)
    for imo in work["imo"].drop_duplicates().sample(6, random_state=0):
        rows = work[work["imo"] == imo]
        one = stage.transform(rows)
        pd.testing.assert_frame_equal(one, full.loc[rows.index], check_exact=False, rtol=1e-9, atol=1e-12)


def test_a_ships_earlier_years_do_not_depend_on_its_later_years(stage, work):
    full = stage.transform(work)
    imo = work.groupby("imo")["year"].nunique().loc[lambda s: s >= 4].index[0]
    rows = work[work["imo"] == imo].sort_values("year")
    cut = rows.iloc[:3]
    pd.testing.assert_series_equal(stage.transform(cut)["persist_prob"], full.loc[cut.index, "persist_prob"], rtol=1e-9, atol=1e-12)


def test_the_stage_fits_inside_the_full_pipeline_and_fills_the_result_table(snapshot, cfg):
    c = copy.deepcopy(cfg)
    c["stages"] = list(c["stages"]) + [SPEC]
    b = ModelBundle.train(snapshot, c)
    r = b.run(snapshot)
    assert r["persist_prob"].between(0, 1).all()
    assert any(s["use"].endswith(":PersistProbability") for s in b.meta["stages"])


def test_without_the_stage_the_columns_are_blank_not_missing(results):
    assert {"persist_prob", "persist_up", "persist_down"} <= set(results.columns) and results["persist_prob"].isna().all()
