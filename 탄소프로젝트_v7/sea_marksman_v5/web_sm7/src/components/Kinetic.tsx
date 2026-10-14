// 소개 화면 공용 연출: 엇갈린 큰 제목, 기울어진 흐르는 띠, 원형 버튼, 줄 목록
import { useRef, type ReactNode } from "react";
import { gsap, reduced, useGsap } from "../motion";

/** 줄마다 들여쓰기가 다른 큰 제목. 스크롤하면 홀수 줄은 오른쪽, 짝수 줄은 왼쪽으로 조금 밀린다 */
export function BigTitle({ lines, as = "h1", className = "" }: { lines: [string, number][]; as?: "h1" | "h2"; className?: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useGsap(ref, () => {
    if (reduced()) return;
    gsap.utils.toArray<HTMLElement>(".bt-l").forEach((el, i) => {
      gsap.fromTo(el, { x: 0 }, { x: (i % 2 ? -1 : 1) * 60, ease: "none", scrollTrigger: { trigger: ref.current, start: "top 30%", end: "bottom top", scrub: true } });
    });
  });
  const H = as;
  return (
    <H ref={ref} className={`bt ${className}`}>
      {lines.map(([t, indent], i) => <span key={i} className="bt-l" style={{ "--i": indent } as React.CSSProperties}>{t}</span>)}
    </H>
  );
}

/** 원 안에 숫자를 넣은 작은 표식 (띠 사이 구분) */
const Badge = ({ n }: { n: string }) => <span className="mq-badge"><span>{n}</span></span>;

/** 기울어진 흐르는 띠. 스크롤에 맞춰 줄마다 반대 방향으로 움직인다 */
export function Marquee({ rows, tone = "dark" }: { rows: { t: string; n?: string }[][]; tone?: "dark" | "light" | "slate" }) {
  const ref = useRef<HTMLDivElement>(null);
  useGsap(ref, () => {
    if (reduced()) return;
    gsap.utils.toArray<HTMLElement>(".mq-row").forEach((el, i) => {
      gsap.fromTo(el, { xPercent: i % 2 ? -28 : 0 }, { xPercent: i % 2 ? 0 : -28, ease: "none", scrollTrigger: { trigger: ref.current, start: "top bottom", end: "bottom top", scrub: true } });
    });
  });
  return (
    <div ref={ref} className={`mq ${tone}`} aria-hidden="true">
      <div className="mq-tilt">
        {rows.map((r, i) => (
          <div key={i} className="mq-row">
            {[...r, ...r, ...r].map((x, j) => <span key={j} className="mq-it">{x.t}{x.n && <Badge n={x.n} />}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}

/** 원형 버튼: 마우스를 올리면 아래에서 채워진다 */
export const RoundBtn = ({ href, children, tone = "dark" }: { href: string; children: ReactNode; tone?: "dark" | "light" }) => (
  <a className={`rbtn ${tone}`} href={href}><span>{children}</span></a>
);

/** 줄 목록 한 줄: 왼쪽 큰 제목, 오른쪽 설명 */
export const Row = ({ head, children, href, n }: { head: ReactNode; children?: ReactNode; href?: string; n?: string }) => {
  const inner = <>{n && <span className="row-n">{n}</span>}<span className="row-h">{head}</span><span className="row-b">{children}</span></>;
  return href ? <a className="row" href={href}>{inner}</a> : <div className="row">{inner}</div>;
};
