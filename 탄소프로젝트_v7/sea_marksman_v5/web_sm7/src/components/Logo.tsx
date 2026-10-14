// Sea Marksman 로고: 조준경 원 + 수평선(조준선) + 선체. 조준선과 수평선이 만나는 곳에 표적 점.
export function LogoMark({ size = 34, dot = "var(--accent, #f0612a)" }: { size?: number; dot?: string }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true" className="logo-mark">
      {/* 조준경 원: 위·아래·오른쪽이 끊긴 세 호 */}
      <path d="M24 5.5a18.5 18.5 0 0 1 17.3 12" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M41.3 30.5A18.5 18.5 0 0 1 24 42.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M17 41.1A18.5 18.5 0 0 1 9.4 12.6" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      {/* 수평선 = 조준선, 왼쪽으로 길게 */}
      <path d="M1.5 24H46.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      {/* 선체 */}
      <path d="M13 28.5h22l-3.6 6.5H16.6z" fill="currentColor" />
      {/* 세로 조준선 */}
      <path d="M24 10v8" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="24" cy="24" r="3.6" fill={dot} />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`logo ${compact ? "compact" : ""}`}>
      <LogoMark />
      <span className="logo-word" aria-label="Sea Marksman">
        <small>SEA</small>
        <b>MARKSMAN</b>
      </span>
    </span>
  );
}
