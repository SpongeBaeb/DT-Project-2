// 소개 화면 머리글(로고·바로가기 2개·메뉴 버튼)과 전체 화면 메뉴
import { useEffect, useState } from "react";
import { Logo } from "./Logo";

export const SITE_MENU: [string, string][] = [
  ["/", "홈"],
  ["/about", "서비스 소개"],
  ["/types", "선종별 현황"],
  ["/list", "2026 리스트"],
  ["/search", "선박 찾기"],
  ["/cost", "비용 계산"],
  ["/my", "내 선박 진단"],
  ["/fleet", "선대 분석"],
  ["/method", "지표와 근거"],
];

const IcoScope = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 2v5M12 17v5M2 12h5M17 12h5" /></svg>;
const IcoShip = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 14h18l-3 6H6z" /><path d="M7 14V9h7l3 5M10 9V5h3" /></svg>;

export function SiteHeader({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const [small, setSmall] = useState(false);
  const [ink, setInk] = useState(false);
  useEffect(() => {
    // 머리글 아래 구역이 밝은 종이 바탕이면 글자를 남색으로
    const f = () => {
      setSmall(window.scrollY > 60);
      const under = document.elementsFromPoint(window.innerWidth / 2, 40).find((e) => e.matches(".s7, .mq, .h7-hero, .sf"));
      setInk(!!under && (under.classList.contains("paper") || under.classList.contains("light")));
    };
    f();
    const t = window.setTimeout(f, 120);
    window.addEventListener("scroll", f, { passive: true });
    return () => { window.clearTimeout(t); window.removeEventListener("scroll", f); };
  }, [path]);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    document.body.classList.toggle("menu-open", open);
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open]);
  return (
    <>
      <header className={`sh ${small && !open ? "small" : ""} ${open ? "open" : ""} ${ink || open ? "ink" : ""}`}>
        <a href="#/" className="sh-logo" aria-label="Sea Marksman 홈"><Logo /></a>
        <nav className="sh-quick" aria-label="바로가기">
          <a href="#/search"><IcoScope />선박 진단 시작</a>
          <a href="#/my"><IcoShip />내 선박 입력</a>
        </nav>
        <button className="sh-burger" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="site-menu" aria-label={open ? "메뉴 닫기" : "메뉴 열기"}>
          <i /><i />
        </button>
      </header>
      <nav id="site-menu" className={`smenu ${open ? "on" : ""}`} aria-hidden={!open} aria-label="전체 메뉴">
        <ol>
          {SITE_MENU.map(([to, label], i) => (
            <li key={to} className={i % 2 ? "l" : "r"}>
              <a href={`#${to}`} tabIndex={open ? 0 : -1} className={path === to || (to !== "/" && path.startsWith(to)) ? "cur" : ""}>
                <span className="smenu-n">{String(i + 1).padStart(2, "0")}</span>
                <span className="smenu-t">{label}</span>
              </a>
            </li>
          ))}
        </ol>
      </nav>
    </>
  );
}
