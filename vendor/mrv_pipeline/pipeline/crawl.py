"""VesselFinder 제원 크롤링 — vessel_scraper_new.py의 수집 로직을 파이프라인에 넣은 것.

python -m pipeline.run --mode version --crawl 처럼 --crawl을 붙였을 때만 실행된다.

- 대상: 최종 패널 선박 중 제원이 없는 IMO (최근 보고연도 선박부터)
- 한 번에 최대 CRAWL_MAX_PER_RUN척, 요청 간격 CRAWL_DELAY_SEC초. 남은 선박은 다음 실행에서 이어서
- 성공한 행만 data/raw/vesselfinder/ship_data_detailed.csv에 추가 (기존 결과 파일과 같은 열, 값은 숫자로)
- 시도 기록은 _crawl_log.csv에 따로 남김 → 실패한 IMO는 CRAWL_RETRY_AFTER_DAYS일 뒤 다시 시도,
  CRAWL_MAX_ATTEMPTS번 실패하면 포기 (VesselFinder에 없는 선박을 매번 다시 요청하지 않도록)
- 기존 크롤러가 남긴 'IMO만 있는 실패 행'은 시도 기록이 없으므로 다시 시도 대상이 된다
- HTTP 403·429(차단·요청 과다)를 받으면 그 실행의 크롤링을 즉시 멈춘다
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

import pandas as pd

from pipeline import config, enrich

log = logging.getLogger("pipeline.crawl")

VF_URL = "https://www.vesselfinder.com/vessels/details/{imo}"
HEADERS = {   # 기존 크롤러와 같음
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
# (페이지의 행 라벨, 저장할 열) — 기존 크롤러의 라벨 그대로 (tr.get_text(strip=True)가 이 문자열로 시작하는 행)
LABELS = [("Year of Build", "Built"), ("Gross Tonnage", "Gross Tonnage"), ("Deadweight(t)", "Summer DWT"),
          ("Length Overall(m)", "Length"), ("Beam(m)", "Beam")]
OUT_COLS = ["IMO", "Built", "Age", "Gross Tonnage", "Summer DWT", "Length", "Beam"]
LOG_COLS = ["imo", "attempted_at", "status", "detail"]
FLUSH_EVERY = 20


class Blocked(Exception):
    pass


def _session():
    import requests

    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def parse_detail(html: str):
    """기존 크롤러 get_ship_info_vf의 파싱 부분. 건조연도가 숫자가 아니어도 다른 값은 살린다."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    data = {k: None for k in OUT_COLS[1:]}
    for tr in soup.find_all("tr"):
        text = tr.get_text(strip=True)
        for label, key in LABELS:
            if text.startswith(label):
                val = text.replace(label, "").strip()
                if val and val != "-":
                    data[key] = val
                    if key == "Built":
                        try:
                            data["Age"] = str(datetime.now().year - int(val))
                        except ValueError:
                            pass
                break
    return data if any(data.values()) else None


def fetch_one(session, imo: str):
    """반환 (status, data, detail). status: ok / no_data / not_found / error. 차단이면 Blocked"""
    try:
        r = session.get(VF_URL.format(imo=imo), timeout=15)
    except Exception as e:
        return "error", None, str(e)[:200]
    if r.status_code in (403, 429):
        raise Blocked(f"HTTP {r.status_code}")
    if r.status_code == 404:
        return "not_found", None, "HTTP 404"
    if r.status_code != 200:
        return "error", None, f"HTTP {r.status_code}"
    data = parse_detail(r.text)
    return ("ok", data, "") if data else ("no_data", None, "")


def to_numbers(data: dict) -> dict:
    """기존 결과 파일과 같은 형식(숫자)으로 저장: '94,724' → 94724.0, '175,000 t' → 175000.0, 못 읽으면 빈칸"""
    out = {}
    for k in OUT_COLS[1:]:
        v = data.get(k)
        m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", "")) if v is not None else None
        out[k] = float(m.group()) if m else float("nan")
    return out


def _log_path(P):
    return P["vf_dir"] / "_crawl_log.csv"


def _out_path(P):
    return P["vf_dir"] / config.VF_OUTPUT_NAME


def load_log(P) -> pd.DataFrame:
    p = _log_path(P)
    if p.exists():
        d = pd.read_csv(p, dtype=str)
        d["attempted_at"] = pd.to_datetime(d["attempted_at"], errors="coerce")
        return d
    return pd.DataFrame(columns=LOG_COLS)


def select_targets(clean: pd.DataFrame, ok_imos: set, crawl_log: pd.DataFrame, now: datetime):
    """제원 없는 패널 선박 중 지금 시도할 수 있는 IMO (처음 시도 → 최근 보고연도 순)"""
    latest = clean.groupby("imo")["year"].max().sort_values(ascending=False, kind="stable")
    fails = crawl_log[crawl_log["status"] != "ok"].groupby("imo").agg(n=("status", "size"),
                                                                       last=("attempted_at", "max"))
    wait = timedelta(days=config.CRAWL_RETRY_AFTER_DAYS)
    rows, gave_up, waiting = [], [], 0
    for imo in latest.index:
        if imo in ok_imos:
            continue
        n = int(fails.at[imo, "n"]) if imo in fails.index else 0
        if n >= config.CRAWL_MAX_ATTEMPTS:
            gave_up.append(imo)
            continue
        if n and pd.notna(fails.at[imo, "last"]) and now - fails.at[imo, "last"] < wait:
            waiting += 1
            continue
        rows.append((n > 0, imo))
    rows.sort(key=lambda t: t[0])                       # 처음 시도하는 선박 먼저 (안정 정렬 → 최근 연도 순 유지)
    return [imo for _, imo in rows], gave_up, waiting


def _append(path, rows, cols):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path, mode="a", header=not path.exists(), index=False)


def run_crawl(clean: pd.DataFrame, P: dict, max_n: int, session=None, sleep=time.sleep, now=None) -> dict:
    now = now or datetime.now()
    session = session or _session()
    ok_imos, _ = enrich.spec_imos(P)
    crawl_log = load_log(P)
    targets, gave_up, waiting = select_targets(clean, ok_imos, crawl_log, now)
    todo = targets[:max_n]
    st = {"eligible": len(targets), "planned": len(todo), "waiting_retry": waiting, "gave_up": len(gave_up),
          "ok": 0, "no_data": 0, "not_found": 0, "error": 0, "blocked": None}
    if not todo:
        return {**st, "remaining": 0}
    log.info("VesselFinder 크롤링: 대상 %d척 중 이번에 %d척 (간격 %.1f초)", len(targets), len(todo), config.CRAWL_DELAY_SEC)

    out_rows, log_rows, done = [], [], 0
    try:
        for i, imo in enumerate(todo, 1):
            try:
                status, data, detail = fetch_one(session, imo)
            except Blocked as e:
                st["blocked"] = str(e)
                log.warning("VesselFinder가 요청을 막음(%s) → 이번 크롤링 중단, 다음 실행에서 이어서", e)
                break
            st[status] += 1
            done += 1
            log_rows.append([imo, now.isoformat(timespec="seconds"), status, detail])
            if data:
                num = to_numbers(data)
                out_rows.append([imo, *[num[c] for c in OUT_COLS[1:]]])
            if i % FLUSH_EVERY == 0:                   # 중간에 끊겨도 받은 만큼은 남도록
                _append(_out_path(P), out_rows, OUT_COLS)
                _append(_log_path(P), log_rows, LOG_COLS)
                out_rows, log_rows = [], []
                log.info("  %d/%d척 (성공 %d)", i, len(todo), st["ok"])
            if i < len(todo):
                sleep(config.CRAWL_DELAY_SEC)
    finally:
        _append(_out_path(P), out_rows, OUT_COLS)
        _append(_log_path(P), log_rows, LOG_COLS)
        st["dedup_removed"] = dedupe_spec_file(_out_path(P))
    st["remaining"] = len(targets) - done
    return st


def dedupe_spec_file(path) -> int:
    """제원 파일의 IMO를 하나로 유지 (노트북 9-4가 IMO 중복이면 멈추므로).
    다시 시도해 성공한 선박의 옛 실패 행(IMO만 있는 행)을 지우고, 같은 IMO가 여러 번이면 마지막 행만 남긴다."""
    if not path.exists():
        return 0
    d = pd.read_csv(path, dtype={"IMO": str})
    if not d["IMO"].duplicated().any():
        return 0
    has = d[[c for c in OUT_COLS[1:] if c in d.columns]].notna().any(axis=1)
    d = d.assign(_has=has, _pos=range(len(d))).sort_values(["IMO", "_has", "_pos"])
    keep = d.drop_duplicates("IMO", keep="last").sort_values("_pos").drop(columns=["_has", "_pos"])
    tmp = path.with_suffix(".tmp")
    keep.to_csv(tmp, index=False)
    tmp.replace(path)
    return len(d) - len(keep)
