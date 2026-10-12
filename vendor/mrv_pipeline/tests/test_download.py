"""다운로드 단계 테스트 — 인터넷 없이 가짜 사이트로 확인.

가짜 사이트는 실제 사이트의 목록 응답(2026-10-06 확인, 2025년 v60)을 그대로 돌려주고,
파일 요청에는 합성 엑셀을 돌려준다. 페이지 나눔(limit)도 실제처럼 흉내 낸다.

    python tests/test_download.py
"""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import config, download, run  # noqa: E402

REAL_LISTING = json.loads("""{"results":[
{"reportingPeriod":2025,"version":60,"generationDate":"05-10-2026 10:09:41","fileName":"2025-v60-05102026-EU MRV Publication of information"},
{"reportingPeriod":2024,"version":246,"generationDate":"01-10-2026 05:24:33","fileName":"2024-v246-01102026-EU MRV Publication of information"},
{"reportingPeriod":2023,"version":92,"generationDate":"29-09-2026 05:08:27","fileName":"2023-v92-29092026-EU MRV Publication of information"},
{"reportingPeriod":2022,"version":241,"generationDate":"06-02-2026 05:24:31","fileName":"2022-v241-06022026-EU MRV Publication of information"},
{"reportingPeriod":2021,"version":219,"generationDate":"25-09-2026 05:10:23","fileName":"2021-v219-25092026-EU MRV Publication of information"},
{"reportingPeriod":2020,"version":210,"generationDate":"25-09-2026 05:07:48","fileName":"2020-v210-25092026-EU MRV Publication of information"},
{"reportingPeriod":2019,"version":228,"generationDate":"13-08-2026 05:08:14","fileName":"2019-v228-13082026-EU MRV Publication of information"},
{"reportingPeriod":2018,"version":275,"generationDate":"29-03-2026 05:12:54","fileName":"2018-v275-29032026-EU MRV Publication of information"}],
"total":8}""")


class FakeResponse:
    def __init__(self, payload=None, content=b"", status=200):
        self._payload, self.content, self.status_code = payload, content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1):
        buf = io.BytesIO(self.content)
        while chunk := buf.read(chunk_size):
            yield chunk


class FakeSite:
    """실제 사이트의 두 요청을 흉내 냄. files: {(연도, 버전): bytes}"""
    def __init__(self, files, listing=REAL_LISTING, broken=False):
        self.files, self.listing, self.broken, self.calls = files, listing, broken, []

    def get(self, url, timeout=None, params=None, stream=False):
        self.calls.append(url)
        if self.broken:
            raise ConnectionError("네트워크 없음")
        if url == download.MRV_LIST_URL:
            page, limit = int(params["page"]), int(params["limit"])
            res = self.listing["results"][(page - 1) * limit: page * limit]
            return FakeResponse({"results": res, "total": self.listing["total"]})
        m = re.search(r"/binary/(\d+)/(\d+)$", url)
        if m and (int(m[1]), int(m[2])) in self.files:
            return FakeResponse(content=self.files[(int(m[1]), int(m[2]))])
        return FakeResponse(content=b"<html>not found</html>", status=200)   # 오류를 HTML로 주는 경우


def main():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        config.SEED_DIR = Path(tmp) / "no_seed"      # 합성 데이터에 실제 번들 제원이 섞이지 않게
        proj, side = Path(tmp) / "proj", Path(tmp) / "side"
        gen = ROOT / "tests" / "make_synthetic_raw.py"
        subprocess.run([sys.executable, gen, proj], check=True, capture_output=True)       # 로컬: 2025 = v58
        subprocess.run([sys.executable, gen, side], check=True, capture_output=True)
        subprocess.run([sys.executable, gen, side, "--add-version", "2025"], check=True, capture_output=True)
        v60_bytes = next(side.glob("data/raw/2025-v59-*.xlsx")).read_bytes()               # 2025 새 버전 내용

        def use(site):
            download._session = lambda: site
            download.time.sleep = lambda s: None
            return site

        # 1) 페이지 나눔: limit=3이어도 8개 연도를 모두 읽는지
        download.PAGE_LIMIT = 3
        site = use(FakeSite({}))
        remote = download.list_remote()
        ok &= check("목록 페이지 나눔 (3개씩 → 8개 연도)", [f.year for f in remote] == list(range(2018, 2026))
                    and len(site.calls) == 3)
        download.PAGE_LIMIT = 50

        # 2) 상태 확인: 2025만 새 버전으로 보이고 아무것도 받지 않음
        site = use(FakeSite({(2025, 60): v60_bytes}))
        code = run.main(["--status", "--root", str(proj)])
        ok &= check("--status는 확인만 (다운로드 없음)", code == 0 and not list(proj.glob("data/raw/2025-v60-*")))

        # 3) 처음 실행(기준 결과) 후, 버전 모드에서 2025 v60만 받아 처리
        run.main(["--mode", "version", "--root", str(proj), "--no-fetch"])
        site = use(FakeSite({(2025, 60): v60_bytes}))
        code = run.main(["--mode", "version", "--root", str(proj)])
        raw = sorted(p.name for p in (proj / "data" / "raw").glob("*.xlsx"))
        binary_calls = [u for u in site.calls if "/binary/" in u]
        ok &= check("버전 모드: 2025 v60 한 개만 다운로드", code == 0 and binary_calls == [download.MRV_FILE_URL.format(year=2025, version=60)])
        ok &= check("원래 파일명으로 저장 + 구버전 archive", "2025-v60-05102026-EU MRV Publication of information.xlsx" in raw
                    and not any(n.startswith("2025-v58") for n in raw)
                    and (proj / "data/raw/archive/2025-v58-15092026-EU MRV Publication of information.xlsx").exists())
        summary = (proj / "reports/pipeline/latest_summary.md").read_text(encoding="utf-8")
        ok &= check("리포트에 사이트 확인 결과", "v58 → v60" in summary and "내려받음" in summary)

        # 4) 다시 실행: 사이트와 로컬이 같으면 목록 요청 1번으로 끝, 결과 그대로
        site = use(FakeSite({(2025, 60): v60_bytes}))
        before = (proj / "data/processed/mrv_clean.csv").stat().st_mtime
        code = run.main(["--mode", "version", "--root", str(proj)])
        ok &= check("변경 없음: 요청 1번, 결과 파일 그대로", code == 0 and len(site.calls) == 1
                    and (proj / "data/processed/mrv_clean.csv").stat().st_mtime == before)

        # 5) 사이트가 엑셀 대신 오류 페이지를 주면: 저장하지 않고 경고 후 로컬로 진행
        listing = json.loads(json.dumps(REAL_LISTING))
        listing["results"][1].update(version=247, fileName="2024-v247-06102026-EU MRV Publication of information")
        use(FakeSite({}, listing=listing))
        code = run.main(["--mode", "version", "--root", str(proj)])
        summary = (proj / "reports/pipeline/latest_summary.md").read_text(encoding="utf-8")
        ok &= check("엑셀이 아닌 응답은 버리고 경고", code == 0 and not list(proj.glob("data/raw/2024-v247*"))
                    and not list(proj.glob("data/raw/*.part")) and "사이트 확인 실패" in summary)

        # 6) 네트워크가 끊겨도 로컬 파일로 진행
        use(FakeSite({}, broken=True))
        code = run.main(["--mode", "version", "--root", str(proj)])
        ok &= check("네트워크 오류 시 로컬로 진행", code == 0)

        # 7) 사이트에 새 보고연도가 생기면: 받아 두고 버전 모드는 멈춤 → 연간 모드 안내
        subprocess.run([sys.executable, gen, side, "--add-year", "2026"], check=True, capture_output=True)
        y26 = next(side.glob("data/raw/2026-*.xlsx")).read_bytes()
        listing = json.loads(json.dumps(REAL_LISTING))
        listing["results"].insert(0, {"reportingPeriod": 2026, "version": 1, "generationDate": "30-06-2027 05:00:00",
                                      "fileName": "2026-v1-30062027-EU MRV Publication of information"})
        listing["total"] = 9
        use(FakeSite({(2026, 1): y26}, listing=listing))
        code = run.main(["--mode", "version", "--root", str(proj)])
        ok &= check("새 연도: 다운로드 후 버전 모드는 멈춤(종료 코드 2)", code == 2 and list(proj.glob("data/raw/2026-v1-*.xlsx")))
        use(FakeSite({}, listing=listing))
        code = run.main(["--mode", "annual", "--root", str(proj)])
        ok &= check("이어서 연간 모드로 처리", code == 0)

    print("다운로드 단계:", "✅ 모두 통과" if ok else "❌ 실패 있음")
    return 0 if ok else 1


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)        # 테스트 출력만 보이게
    sys.exit(main())
