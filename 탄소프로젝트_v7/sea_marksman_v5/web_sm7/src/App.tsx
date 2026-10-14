// Sea Marksman: 같은 E등급이라도 이유는 배마다 다르다.
//   소개 화면(홈·서비스 소개·선종·리스트·지표와 근거): 큰 글씨·스크롤 연출
//   서비스 화면(찾기·진단·리스트 표·선대·비용·내 선박·비교·관심): 왼쪽 메뉴가 있는 분석 화면
import { useEffect, useMemo, useState } from "react";
import { loadMeta, loadShips, type Meta, type Ship } from "./data";
import { mergeMarket, refreshMarket } from "./market";
import { setPrices, usePrices, useRoute, useTheme } from "./store";
import { scrollTop, useSmoothScroll } from "./motion";
import PriceSheet from "./components/PriceSheet";
import { SiteHeader } from "./components/SiteNav";
import { AppShell } from "./components/AppShell";
import { Logo } from "./components/Logo";
import Home7 from "./pages/Home7";
import About from "./pages/About";
import { TypeDetail, Types } from "./pages/Types";
import List7 from "./pages/List7";
import Search from "./pages/Search";
import Diagnosis from "./pages/Diagnosis";
import Cost from "./pages/Cost";
import Fleet from "./pages/Fleet";
import MyShip from "./pages/MyShip";
import List from "./pages/List";
import Compare from "./pages/Compare";
import Watch from "./pages/Watch";
import Method from "./pages/Method";
import { BigTitle } from "./components/Kinetic";

const SITE = new Set(["", "about", "types", "list", "method"]);
const APP_TITLE: Record<string, string> = {
  search: "선박 찾기", ship: "선박 진단", table: "2026 리스트", fleet: "선대 분석", cost: "비용 계산", my: "내 선박 진단", compare: "선박 비교", watch: "관심 목록",
};

function SiteFooter({ meta }: { meta: Meta | null }) {
  return (
    <footer className="sf">
      <div className="w7">
        <div className="sf-top">
          <Logo />
          <nav aria-label="바닥 메뉴">
            <a href="#/about">서비스 소개</a><a href="#/types">선종별 현황</a><a href="#/list">2026 리스트</a><a href="#/search">선박 찾기</a><a href="#/method">지표와 근거</a>
          </nav>
        </div>
        <p>자료: EU THETIS-MRV 2018–{meta?.base_year ?? 2025} 공개 보고(총톤수 5,000 이상, EU 관련 항해만), 공개 선박 제원. CII 등급은 MRV 자료로 계산한 근사값이며 공식 등급과 다를 수 있습니다. 요인별 기여는 통계적 연관이며 인과가 아닙니다.</p>
        {meta && <p className="sf-ver">모델 {meta.model_version} · 데이터 {meta.data_hash} · {meta.generated}</p>}
      </div>
    </footer>
  );
}

export default function App() {
  const { path, query } = useRoute();
  const [ships, setShips] = useState<Ship[] | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);
  const prices = usePrices();
  const theme = useTheme();
  const seg = path.split("/");
  const page = seg[1] || "";
  const site = SITE.has(page);
  useEffect(() => {
    Promise.all([loadShips(), loadMeta()]).then(([s, m]) => { setShips(s); setMeta(m); }).catch((e) => setErr(String(e.message ?? e)));
  }, []);
  useEffect(() => {
    if (!meta) return;
    refreshMarket().then((s) => setPrices(mergeMarket(prices, s.points, meta)));
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { document.documentElement.dataset.theme = site ? "light" : theme; document.documentElement.dataset.mode = site ? "site" : "app"; }, [site, theme]);
  useEffect(() => { scrollTop(); }, [path]);
  useSmoothScroll(site);
  const cur = useMemo(() => (ships && meta ? ships.filter((s) => s.ly === meta.base_year) : null), [ships, meta]);

  if (err) return <div className="boot"><h1>데이터를 불러오지 못했습니다</h1><p>{err}</p></div>;
  if (!ships || !meta || !cur) return <div className="boot" aria-live="polite"><Logo /><p>데이터를 불러오는 중</p></div>;

  if (site) {
    let body;
    if (page === "about") body = <About meta={meta} />;
    else if (page === "types" && seg[2]) body = <TypeDetail key={seg[2]} ships={cur} meta={meta} t={seg[2]} />;
    else if (page === "types") body = <Types ships={cur} />;
    else if (page === "list") body = <List7 key={query.toString()} ships={cur} meta={meta} query={query} />;
    else if (page === "method") body = (
      <>
        <section className="s7 paper page7-top"><div className="w7"><BigTitle lines={[["지표와 근거", 0]]} /><p className="lead7">무엇을 어떻게 계산했는지, 모델이 얼마나 맞았는지, 어떤 자료와 서버를 쓰는지 정리했습니다.</p></div></section>
        <section className="s7 paper method7"><Method meta={meta} /></section>
      </>
    );
    else body = <Home7 ships={cur} meta={meta} />;
    return (
      <div className="site">
        <a className="skip" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>본문으로</a>
        <SiteHeader path={path} />
        <main id="main" tabIndex={-1} key={path}>{body}</main>
        <SiteFooter meta={meta} />
      </div>
    );
  }

  let body;
  if (page === "search") body = <Search key={query.toString()} ships={ships} meta={meta} query={query} />;
  else if (page === "ship") body = <Diagnosis key={seg[2]} ships={ships} meta={meta} imo={Number(seg[2])} />;
  else if (page === "table") body = <List key={query.toString()} ships={cur} meta={meta} query={query} />;
  else if (page === "cost") body = <Cost key={query.get("imo") ?? ""} ships={ships} meta={meta} imo={Number(query.get("imo")) || undefined} onPrices={() => setSheet(true)} />;
  else if (page === "fleet") body = <Fleet ships={cur} meta={meta} />;
  else if (page === "my") body = <MyShip key={query.toString()} ships={ships} meta={meta} imo={Number(query.get("imo")) || undefined} />;
  else if (page === "compare") body = <Compare ships={ships} meta={meta} />;
  else if (page === "watch") body = <Watch ships={ships} meta={meta} />;
  else body = <div className="wrap pad"><h2>없는 화면입니다</h2><p><a href="#/">홈으로</a></p></div>;
  return (
    <>
      <AppShell page={page} title={APP_TITLE[page] ?? "Sea Marksman"} onPrices={() => setSheet(true)}>{body}</AppShell>
      <PriceSheet open={sheet} onClose={() => setSheet(false)} meta={meta} />
    </>
  );
}
