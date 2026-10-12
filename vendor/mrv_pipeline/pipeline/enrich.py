"""선박 제원 파일 관련 도우미. 제원을 붙이는 규칙 자체는 rules_mrv.py 9단계(노트북 9-1~9-4)에 있다.

- 제원 파일: data/raw/vesselfinder/ship_data_detailed.csv (노트북 9-1과 같은 위치·형식)
- 크롤링할 IMO 목록(missing_spec_imo_list.txt): 정제 결과 선박 중 제원 파일에 없고 시도한 적도 없는 IMO
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from pipeline import config

log = logging.getLogger("pipeline.enrich")

SPEC_VALUE_COLS = ["Built", "Gross Tonnage", "Summer DWT", "Length", "Beam"]


def spec_path(P) -> Path:
    return P["vf_dir"] / config.VF_OUTPUT_NAME


def ensure_spec_file(P):
    """파이프라인에 들어 있는 번들 제원 파일(seed)을 data/raw/vesselfinder/에 반영.
    노트북 9-1과 크롤러가 같은 위치를 쓰므로, 번들 파일을 직접 읽지 않고 제자리에 놓고 쓴다.
    - 제원 파일이 없으면 seed를 그대로 복사
    - 있으면 '제원 값이 없는 IMO'(파일에 없거나 크롤링 실패로 IMO만 남은 행)의 seed 행만 덧붙임.
      제원 값이 있는 기존 행은 그대로 둔다 (팀원이 고친 값이나 새로 크롤링한 값을 덮어쓰지 않음)
    반환: 파일을 바꿨으면 안내 문장, 아니면 None"""
    import shutil

    from pipeline import crawl          # crawl이 enrich를 불러오므로 함수 안에서 불러옴

    dest = spec_path(P)
    seed = config.SEED_DIR / config.VF_OUTPUT_NAME
    if not seed.exists():
        return None
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed, dest)
        n = sum(1 for _ in open(dest, encoding="utf-8", errors="ignore")) - 1
        return f"제원 파일이 없어 파이프라인에 들어 있는 파일({n:,}척)을 {dest}에 복사함"

    cur = read_spec(P)
    sd = pd.read_csv(seed, dtype={"IMO": str})
    ok, _ = spec_imos(P)
    cols = [c for c in SPEC_VALUE_COLS if c in sd.columns]
    add = sd[sd[cols].notna().any(axis=1) & sd["IMO"].notna() & ~sd["IMO"].isin(ok)]
    if add.empty:
        return None
    if dest.read_bytes()[-1:] not in (b"\n", b""):   # 마지막 줄에 줄바꿈이 없으면 붙인 뒤 덧붙임
        with open(dest, "ab") as f:
            f.write(b"\n")
    add.reindex(columns=cur.columns).to_csv(dest, mode="a", header=False, index=False)
    replaced = crawl.dedupe_spec_file(dest)           # IMO만 남은 옛 실패 행은 seed 행이 대신함
    return (f"파이프라인에 들어 있는 제원 파일에서 기존 제원 파일에 제원 값이 없던 {len(add):,}척을 {dest}에 추가함"
            + (f" (크롤링 실패로 IMO만 있던 행 {replaced}개 대체)" if replaced else ""))


def read_spec(P):
    p = spec_path(P)
    if not p.exists():
        return None
    return pd.read_csv(p, dtype={"IMO": str})


def spec_imos(P):
    """반환 (제원 값이 하나라도 있는 IMO, 제원 파일에 있는 모든 IMO = 시도한 IMO)"""
    spec = read_spec(P)
    if spec is None:
        return set(), set()
    cols = [c for c in SPEC_VALUE_COLS if c in spec.columns]
    has = spec[cols].notna().any(axis=1)
    return set(spec.loc[has, "IMO"].dropna()), set(spec["IMO"].dropna())


def spec_status(clean: pd.DataFrame, P: dict):
    """정제 결과 선박 기준 제원 현황과 크롤링할 IMO 목록"""
    ships = set(clean["imo"].astype(str))
    ok, attempted = spec_imos(P)
    log_p = P["vf_dir"] / "_crawl_log.csv"
    if log_p.exists():
        attempted |= set(pd.read_csv(log_p, dtype=str)["imo"].dropna())
    missing = sorted(ships - attempted)
    return {"ships": len(ships), "with_specs": len(ships & ok), "never_crawled": len(missing),
            "crawled_but_failed": len((ships & attempted) - ok)}, missing


def write_missing_list(missing: list, P: dict) -> list[str]:
    """크롤러 입력 형식(IMO 한 줄에 하나)으로 저장. 크롤러 경로가 있으면 거기에도 저장."""
    written = []
    targets = [P["missing_spec_list"]]
    crawler = Path(config.CRAWLER_INPUT_TXT) if config.CRAWLER_INPUT_TXT else None
    if crawler and crawler.is_absolute() and crawler.parent.exists():
        targets.append(crawler)
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
        written.append(str(t))
    return written
