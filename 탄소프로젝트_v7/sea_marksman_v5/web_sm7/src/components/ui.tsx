// 공용 부품: 등장 효과, 판정 배지, CII 칩, 착시 신호, 점검 아이콘, 로고, 도움말
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Grade, Meta, SignalKey } from "../data";
import { LIST_NAME } from "../data";
import { VERDICT, type VerdictKey } from "../verdict";

export function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) { setOn(true); return; }
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setOn(true), io.disconnect()), { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return <div ref={ref} className={`reveal ${on ? "on" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>{children}</div>;
}

/** 조준경 아이콘 (로고·판정 배지 공용) */
export const ScopeIcon = ({ dot = "#e0532c" }: { dot?: string }) => (
  <svg viewBox="0 0 32 32" aria-hidden="true">
    <circle cx="16" cy="16" r="10.5" fill="none" stroke="currentColor" strokeWidth="2.4" />
    <path d="M16 2v8M16 22v8M2 16h8M22 16h8" stroke="currentColor" strokeWidth="2.4" />
    <circle cx="16" cy="16" r="3" fill={dot} />
  </svg>
);

export const Mark = () => <ScopeIcon dot="#ff7a55" />;

export function Verdict({ k, lg }: { k: VerdictKey; lg?: boolean }) {
  return <span className={`vd vd-${k} ${lg ? "lg" : ""}`} title={VERDICT[k].line}><ScopeIcon dot="currentColor" />{VERDICT[k].name}</span>;
}

export const Grade_ = ({ g, sm }: { g?: Grade; sm?: boolean }) =>
  g ? <span className={`cii g${g} ${sm ? "sm" : ""}`} aria-label={`CII ${g}등급`}>{g}</span> : <span className="muted small">–</span>;

/** 착시 신호를 쉬운 말로 */
export const SIGNAL_PLAIN: Record<SignalKey, [string, string]> = {
  berth: ["정박", "정박 배출이 같은 조건 예측값 또는 해당 선박 예년 대비 2σ 이상"],
  short: ["짧은 구간", "EU 해상 시간 500시간 미만으로 연간 값 변동이 큼"],
  fuel: ["연료", "연료 1톤당 CO₂ 3.05 미만 (화석연료 범위 밖, LNG 등 대체연료 추정)"],
  report: ["보고 오류", "적재량이 재화중량 × 1.2 초과 또는 평균 속력 3노트 미만"],
  special: ["특수 운항", "셔틀 탱커 운영사 등 운항 형태가 다른 집단"],
};

export function Signals({ sig, none = "없음" }: { sig?: SignalKey[]; meta?: Meta; none?: string }) {
  if (!sig?.length) return <span className="muted small">{none}</span>;
  return <span className="sgns">{sig.map((k) => <span key={k} className={`sgn ${k === "berth" ? "berth" : ""}`} title={SIGNAL_PLAIN[k][1]}>{SIGNAL_PLAIN[k][0]}</span>)}</span>;
}

export const CheckIcon = ({ ok }: { ok: boolean }) =>
  ok ? (
    <svg viewBox="0 0 18 18" className="ic" aria-label="정상"><circle cx="9" cy="9" r="8" fill="var(--base-wash)" /><path d="M5 9.2l2.6 2.6L13 6.4" fill="none" stroke="var(--base)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
  ) : (
    <svg viewBox="0 0 18 18" className="ic" aria-label="확인 필요"><circle cx="9" cy="9" r="8" fill="var(--amber-wash)" /><path d="M9 4.6v5.2" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round" /><circle cx="9" cy="13" r="1.2" fill="var(--amber)" /></svg>
  );

export function Card({ title, sub, children, className = "", id, style }: { title?: ReactNode; sub?: ReactNode; children: ReactNode; className?: string; id?: string; style?: React.CSSProperties }) {
  return (
    <div className={`card ${className}`} id={id} style={style}>
      {title && <div className="card-h"><h3>{title}</h3>{sub && <span className="small muted">{sub}</span>}</div>}
      {children}
    </div>
  );
}

export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => <div className="empty"><h3>{title}</h3>{children}</div>;

export function Help({ children, label = "산정 기준" }: { children: ReactNode; label?: string }) {
  return <details className="help"><summary>{label}</summary><div>{children}</div></details>;
}

export const SearchIcon = () => (
  <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="6" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M13 13l5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
);

/** 다음 해 리스트 배지 */
export const ListBadge = ({ k }: { k?: "target" | "watch" }) =>
  k ? <span className={`lb lb-${k}`} title={k === "target" ? "다음 해 CII D·E 확률이 기준 이상" : "현재 A~C등급이나 다음 해 감축 요구 미달 가능성이 높음"}>{LIST_NAME[k]}</span> : null;

/** 확률 0~1 → 정수 % */
export const prob = (p?: number | null) => (p === undefined || p === null ? "–" : `${Math.round(p * 100)}%`);
