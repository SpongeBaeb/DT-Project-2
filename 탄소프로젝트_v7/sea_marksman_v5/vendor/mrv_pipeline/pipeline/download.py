"""THETIS-MRV 사이트에서 새 버전 엑셀을 직접 내려받는다.

사이트 화면(#public/emission-report)이 내부적으로 쓰는 요청 두 개를 그대로 호출한다 (로그인 불필요).
  - 목록: GET {MRV_LIST_URL}?page=1&limit=..  → {"results": [{reportingPeriod, version, generationDate, fileName}], "total": n}
  - 파일: GET {MRV_FILE_URL}.format(year=.., version=..)  → xlsx

동작: 목록 조회(요청 1번) → 로컬 data/raw보다 버전이 높은 연도와 새 연도만 다운로드 → 검사 후 원래 파일명으로 저장.
변경이 없으면 목록 요청 한 번으로 끝난다.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pipeline import config

log = logging.getLogger("pipeline.download")

MRV_LIST_URL = "https://mrv.emsa.europa.eu/api/public-emission-report/downloadable-files"
MRV_FILE_URL = "https://mrv.emsa.europa.eu/api/public-emission-report/reporting-period-document/binary/{year}/{version}"
PAGE_LIMIT = 50
HEADERS = {"User-Agent": "ship-carbon-ml MRV pipeline (research use)", "Accept": "application/json, */*"}
TIMEOUT_LIST, TIMEOUT_FILE = 60, 600
RETRIES = 3
MIN_FILE_BYTES = 50_000          # 이보다 작으면 오류 페이지 등으로 보고 버림


@dataclass
class RemoteFile:
    year: int
    version: int
    generated: str      # YYYY-MM-DD HH:MM:SS
    file_name: str      # 확장자 포함

    @property
    def url(self):
        return MRV_FILE_URL.format(year=self.year, version=self.version)


def _session():
    import requests

    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get(session, url, timeout, **kw):
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = session.get(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except Exception as e:          # 네트워크 일시 오류 → 잠깐 쉬고 재시도
            last = e
            if attempt < RETRIES:
                time.sleep(3 * attempt)
    raise RuntimeError(f"요청 실패 ({RETRIES}회): {url} — {last}")


def _to_remote(item) -> RemoteFile:
    year, version = int(item["reportingPeriod"]), int(item["version"])
    gen = datetime.strptime(item["generationDate"], "%d-%m-%Y %H:%M:%S")
    name = f"{item.get('fileName') or ''}".strip()
    name = name if name.lower().endswith(".xlsx") else f"{name}.xlsx"
    if not re.match(config.FILE_PATTERN, name):      # 파일명 규칙이 바뀌어도 파이프라인이 읽을 수 있게 맞춤
        fixed = f"{year}-v{version}-{gen:%d%m%Y}-EU MRV Publication of information.xlsx"
        log.warning("사이트 파일명 '%s'이 예상 형식과 달라 '%s'로 저장", name, fixed)
        name = fixed
    return RemoteFile(year, version, f"{gen:%Y-%m-%d %H:%M:%S}", name)


def list_remote(session=None) -> list[RemoteFile]:
    """사이트에 공개된 연도별 최신 파일 목록 (여러 페이지면 모두 읽음)"""
    session = session or _session()
    items, page = [], 1
    while True:
        r = _get(session, MRV_LIST_URL, TIMEOUT_LIST,
                 params={"_dc": int(time.time() * 1000), "page": page, "limit": PAGE_LIMIT})
        data = r.json()
        batch = data.get("results") or []
        items += batch
        if not batch or len(items) >= int(data.get("total", len(items))) or page >= 20:
            break
        page += 1
    remote = [_to_remote(i) for i in items]
    latest = {}
    for f in remote:                    # 같은 연도가 여러 번 나오면 가장 높은 버전만
        if f.year not in latest or f.version > latest[f.year].version:
            latest[f.year] = f
    return [latest[y] for y in sorted(latest)]


def plan(remote: list[RemoteFile], local: dict) -> tuple[list[RemoteFile], list[str]]:
    """local: {연도: sources.RawFile}. 반환 (받을 파일, 참고 메시지)"""
    todo, notes = [], []
    for f in remote:
        if f.year < config.FIRST_YEAR:
            continue
        cur = local.get(f.year)
        if cur is None:
            todo.append(f)
            notes.append(f"{f.year}년: 사이트에 새 보고연도 v{f.version} ({f.generated})")
        elif f.version > cur.version:
            todo.append(f)
            notes.append(f"{f.year}년: v{cur.version} → v{f.version} ({f.generated})")
        elif f.version < cur.version:
            notes.append(f"{f.year}년: 로컬 v{cur.version}이 사이트 v{f.version}보다 높음 — 확인 필요")
    return todo, notes


def _looks_like_xlsx(path: Path) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(4)
    return head == b"PK\x03\x04" and path.stat().st_size >= MIN_FILE_BYTES


def download(f: RemoteFile, raw_dir: Path, session=None) -> Path:
    """임시 파일(.part)로 받은 뒤 xlsx인지 확인하고 원래 이름으로 바꾼다 (중간에 끊겨도 반쪽 파일이 남지 않음)"""
    session = session or _session()
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f.file_name
    tmp = raw_dir / (f.file_name + ".part")
    log.info("다운로드: %s", f.file_name)
    r = _get(session, f.url, TIMEOUT_FILE, stream=True)
    with open(tmp, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            if chunk:
                fh.write(chunk)
    if not _looks_like_xlsx(tmp):
        size = tmp.stat().st_size
        tmp.unlink()
        raise RuntimeError(f"{f.file_name}: 받은 내용이 엑셀 파일이 아님 ({size} bytes)")
    tmp.replace(dest)
    return dest


def cleanup_partial(raw_dir: Path):
    for p in raw_dir.glob("*.part"):
        p.unlink()


def fetch_updates(raw_dir: Path, local: dict, dry_run=False, session=None):
    """목록 조회 → 새 버전만 다운로드. 반환 (받은 파일명 목록, 메시지 목록)"""
    session = session or _session()
    cleanup_partial(raw_dir)
    remote = list_remote(session)
    todo, notes = plan(remote, local)
    if not todo:
        return [], notes or [f"사이트와 로컬이 같음 (사이트 {len(remote)}개 연도 확인)"]
    if dry_run:
        return [], notes
    got = []
    for f in todo:
        got.append(download(f, raw_dir, session).name)
    return got, notes
