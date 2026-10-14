// 서비스 화면 틀 (2번 예시 화면 기준): 왼쪽 아이콘 메뉴, 위쪽 제목줄, 짙은 패널
import type { ReactNode } from "react";
import { LogoMark } from "./Logo";
import { pricesReady } from "../calc";
import { setTheme, useCompare, usePrices, useTheme, useWatch } from "../store";

const P = (d: string) => <path d={d} />;
const ICONS: Record<string, ReactNode> = {
  search: <>{P("M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.5 15.5 21 21")}</>,
  table: <>{P("M3 5h18M3 12h18M3 19h18M8 5v14")}</>,
  fleet: <>{P("M3 15h18l-3 5H6zM7 15v-4h6l3 4M10 11V7h3")}</>,
  cost: <>{P("M12 3v18M16.5 7.5C16 5.8 14.3 5 12 5s-4.5 1-4.5 3 2 2.6 4.5 3 4.5 1 4.5 3.2S14.6 18 12 18s-4.2-1-4.6-2.7")}</>,
  my: <>{P("M12 3 3 8v1h18V8zM5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18")}</>,
  compare: <>{P("M7 4v16M17 4v16M3 8h8M13 16h8")}</>,
  watch: <>{P("M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z")}</>,
  method: <>{P("M5 4h11l3 3v13H5zM9 10h6M9 14h6")}</>,
  home: <>{P("M4 11 12 4l8 7v9h-5v-6H9v6H4z")}</>,
};
const Ico = ({ k }: { k: string }) => <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[k]}</svg>;

const NAV: [string, string, string][] = [
  ["search", "선박 찾기", "/search"], ["table", "2026 리스트", "/table"], ["fleet", "선대 분석", "/fleet"], ["cost", "비용 계산", "/cost"],
  ["my", "내 선박 진단", "/my"], ["compare", "비교", "/compare"], ["watch", "관심 목록", "/watch"],
];

export function AppShell({ page, title, onPrices, children }: { page: string; title: string; onPrices: () => void; children: ReactNode }) {
  const cmp = useCompare(), watch = useWatch(), theme = useTheme(), prices = usePrices();
  const active = page === "ship" ? "search" : page;
  return (
    <div className="ax">
      <aside className="ax-side" aria-label="서비스 메뉴">
        <a href="#/" className="ax-logo" aria-label="Sea Marksman 홈"><LogoMark size={30} /><span>SEA<br />MARKSMAN</span></a>
        <nav>
          {NAV.map(([k, l, to]) => (
            <a key={k} href={`#${to}`} className={active === k ? "on" : ""} aria-current={active === k ? "page" : undefined}>
              <Ico k={k} /><span>{l}</span>
              {k === "compare" && cmp.length > 0 && <em>{cmp.length}</em>}
              {k === "watch" && watch.length > 0 && <em>{watch.length}</em>}
            </a>
          ))}
        </nav>
        <nav className="ax-low">
          <a href="#/method" className={active === "method" ? "on" : ""}><Ico k="method" /><span>지표와 근거</span></a>
          <a href="#/"><Ico k="home" /><span>소개 화면</span></a>
        </nav>
      </aside>
      <div className="ax-main">
        <div className="ax-bar">
          <h1 className="ax-title">{title}</h1>
          <div className="ax-tools">
            <button className={`ax-pill ${pricesReady(prices) ? "ok" : ""}`} onClick={onPrices}>{pricesReady(prices) ? "가격 · 환율" : "가격 입력"}</button>
            <button className="ax-pill" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "밝은 화면으로" : "어두운 화면으로"}>{theme === "dark" ? "밝게" : "어둡게"}</button>
          </div>
        </div>
        <div className="ax-body">{children}</div>
      </div>
    </div>
  );
}
