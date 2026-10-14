"""--crawl 단계 테스트 — 인터넷 없이 가짜 VesselFinder로 확인.

    python tests/test_crawl.py
"""
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import config, crawl, run  # noqa: E402


def page(built, gt, dwt, loa, beam):
    """VesselFinder 상세 페이지 표 구조 흉내: 라벨의 단위가 별도 태그라 get_text(strip=True)가 'Deadweight(t)'가 됨"""
    return f"""<html><body><table class="tparams">
      <tr><td class="n3">Gross Tonnage</td><td class="v3">{gt}</td></tr>
      <tr><td class="n3">Deadweight<span> (t)</span></td><td class="v3">{dwt}</td></tr>
      <tr><td class="n3">Length Overall<span> (m)</span></td><td class="v3">{loa}</td></tr>
      <tr><td class="n3">Beam<span> (m)</span></td><td class="v3">{beam}</td></tr>
      <tr><td class="n3">Year of Build</td><td class="v3">{built}</td></tr></table></body></html>"""


class Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class FakeVF:
    """IMO 끝자리로 응답을 정함: 0~5 성공, 6 제원 없는 페이지, 7 404, 8 일시 오류, 9 성공. block_after면 그 뒤 429"""
    def __init__(self, block_after=None):
        self.calls, self.block_after = [], block_after

    def get(self, url, timeout=None):
        imo = url.rsplit("/", 1)[-1]
        self.calls.append(imo)
        if self.block_after is not None and len(self.calls) > self.block_after:
            return Resp(429)
        d = int(imo[-1])
        if d == 6:
            return Resp(200, "<html><table><tr><td>Name</td><td>X</td></tr></table></html>")
        if d == 7:
            return Resp(404)
        if d == 8:
            raise ConnectionError("timeout")
        return Resp(200, page(2000 + d, f"{40000 + d:,}", "75,000", "229", "32.3"))


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


def main():
    ok = True
    crawl.time.sleep = lambda s: None
    with tempfile.TemporaryDirectory() as tmp:
        config.SEED_DIR = Path(tmp) / "no_seed"      # 합성 데이터에 실제 번들 제원이 섞이지 않게
        proj = Path(tmp) / "proj"
        subprocess.run([sys.executable, ROOT / "tests" / "make_synthetic_raw.py", proj], check=True, capture_output=True)
        assert run.main(["--mode", "version", "--root", str(proj), "--no-fetch"]) == 0     # 기준 결과
        vf_dir = proj / "data" / "raw" / "vesselfinder"
        out, logf = vf_dir / config.VF_OUTPUT_NAME, vf_dir / "_crawl_log.csv"
        clean = pd.read_pickle(proj / "data/processed/_state/mrv_clean.pkl")
        imos = sorted(clean["imo"].unique())

        # 기존 크롤러 결과: 앞 40척 중 5척은 IMO만 있는 실패 행
        vf_dir.mkdir(parents=True, exist_ok=True)
        rows = [{"IMO": i} if k % 8 == 0 else {"IMO": i, "Built": "2010", "Age": "16", "Gross Tonnage": "30000",
                                                "Summer DWT": "50000", "Length": "190", "Beam": "32"}
                for k, i in enumerate(imos[:40])]
        pd.DataFrame(rows).to_csv(out, index=False)
        old_fail = {r["IMO"] for r in rows if "Built" not in r}

        # 1) 라벨 파싱 (기존 크롤러와 같은 결과)
        d = crawl.parse_detail(page(2007, "94,724", "175,000", "299.92", "48.2"))
        ok &= check("페이지 파싱: 기존 크롤러와 같은 값", d["Built"] == "2007" and d["Gross Tonnage"] == "94,724"
                    and d["Summer DWT"] == "175,000" and d["Length"] == "299.92" and d["Beam"] == "48.2")

        # 2) --crawl --crawl-max 50: 50척만, 성공만 결과 파일에, 시도는 모두 기록
        site = FakeVF()
        crawl._session = lambda: site
        assert run.main(["--mode", "version", "--root", str(proj), "--no-fetch", "--crawl", "--crawl-max", "50"]) == 0
        res, lg = pd.read_csv(out, dtype=str), pd.read_csv(logf, dtype=str)
        ok_set = set(lg.loc[lg.status == "ok", "imo"])
        new_ok = res[res["IMO"].isin(ok_set)]
        ok &= check("한 번에 최대 50척", len(site.calls) == 50 and len(lg) == 50)
        ok &= check("값은 기존 파일처럼 숫자로 저장 ('40,003' → 40003.0)",
                    pd.to_numeric(new_ok["Gross Tonnage"], errors="coerce").notna().all()
                    and new_ok["Gross Tonnage"].str.fullmatch(r"\d+\.\d+").all())
        with_data = set(res.loc[res[crawl.OUT_COLS[1:]].notna().any(axis=1), "IMO"])
        new_fail = set(lg.loc[lg.status != "ok", "imo"]) - old_fail
        ok &= check("성공한 선박만 결과 파일에 추가 (기존 형식 그대로)",
                    list(res.columns) == crawl.OUT_COLS and with_data == (set(imos[:40]) - old_fail) | ok_set
                    and not new_fail & set(res["IMO"]))
        tg, _, _ = crawl.select_targets(clean, set(imos[:40]) - old_fail, crawl.load_log(run.config.paths()), datetime.now())
        ok &= check("기존 실패 행(IMO만)도 다시 시도 대상", old_fail <= set(tg))
        ok &= check("이미 제원 있는 선박은 시도 안 함", not (set(imos[:40]) - old_fail) & set(site.calls))
        panel = pd.read_pickle(proj / "data/processed/_state/mrv_clean.pkl")
        summary = (proj / "reports/pipeline/latest_summary.md").read_text(encoding="utf-8")
        ok &= check("리포트에 크롤링 결과", "VesselFinder 크롤링" in summary and "남은 대상" in summary)
        p = pd.read_csv(proj / "data/processed/mrv_merged.csv", dtype={"imo": str})
        ok &= check("새로 받은 제원이 같은 실행에서 통합 파일(9단계)에 붙고 CII 계산까지",
                    p.loc[p.imo.isin(set(new_ok["IMO"])), "gross_tonnage"].notna().all()
                    and p.loc[p.imo.isin(set(new_ok["IMO"])), "cii_rating_2026basis"].notna().any())
        ok &= check("제원 파일 IMO 중복 없음 (다시 시도해 성공한 옛 실패 행은 지움)", not res["IMO"].duplicated().any()
                    and not pd.read_csv(out, dtype=str)["IMO"].duplicated().any())

        # 3) 바로 다시 실행: 실패한 선박은 기다리고, 아직 안 한 선박을 이어서
        site2 = FakeVF()
        crawl._session = lambda: site2
        run.main(["--mode", "version", "--root", str(proj), "--no-fetch", "--crawl", "--crawl-max", "50"])
        failed1 = set(lg.loc[lg.status != "ok", "imo"])
        ok &= check("실패한 선박은 7일 안에 다시 시도 안 함", not failed1 & set(site2.calls) and len(site2.calls) == 50)

        # 4) 8일 뒤: 실패한 선박을 다시 시도, 3번 실패하면 포기
        lgall = pd.read_csv(logf, dtype=str)
        for days in (8, 16, 24):
            site3 = FakeVF()
            crawl._session = lambda: site3
            run.config.set_root(proj)
            stt = crawl.run_crawl(clean, run.config.paths(), 1000, session=site3, sleep=lambda s: None,
                                  now=datetime.now() + timedelta(days=days))
        lgall = pd.read_csv(logf, dtype=str)
        n_fail = lgall[lgall.status != "ok"].groupby("imo").size()
        ok &= check("실패는 최대 3번까지만 시도", n_fail.max() == config.CRAWL_MAX_ATTEMPTS and stt["gave_up"] > 0)

        # 5) 차단(429)이면 그 자리에서 멈추고 실행은 성공으로 끝남
        crawl_log_before = len(lgall)
        site4 = FakeVF(block_after=3)
        crawl._session = lambda: site4
        Path(logf).unlink()                       # 다시 시도할 대상이 생기도록 기록 초기화
        code = run.main(["--mode", "version", "--root", str(proj), "--no-fetch", "--crawl", "--crawl-max", "50"])
        summary = (proj / "reports/pipeline/latest_summary.md").read_text(encoding="utf-8")
        ok &= check("차단(429)이면 즉시 멈춤, 실행은 계속", code == 0 and len(site4.calls) == 4 and "막아" in summary)

    print("크롤링 단계:", "✅ 모두 통과" if ok else "❌ 실패 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    sys.exit(main())
