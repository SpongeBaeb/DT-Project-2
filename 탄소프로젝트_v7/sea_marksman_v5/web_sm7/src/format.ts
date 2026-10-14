// 숫자 표기. 표와 그래프는 같은 규칙을 쓴다.
export const num = (v?: number | null, d = 0) => (v === undefined || v === null || !Number.isFinite(v) ? "–" : v.toLocaleString("ko-KR", { maximumFractionDigits: d, minimumFractionDigits: d }));
export const pct = (v?: number | null, d = 0) => (v === undefined || v === null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(d)}%`);
export const pp = (v?: number | null, d = 1) => (v === undefined || v === null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(d)}%p`);
export const times = (v?: number | null) => (v === undefined || v === null ? "–" : v >= 10 ? `${v.toFixed(0)}배` : `${v.toFixed(1)}배`);
/** 원 단위 → 억·만 원 */
export function krw(v?: number): string {
  if (v === undefined || !Number.isFinite(v)) return "–";
  const s = v < 0 ? "−" : "", a = Math.abs(v);
  if (a >= 1e8) return `${s}${(a / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: a >= 1e10 ? 0 : 1 })}억 원`;
  if (a >= 1e4) return `${s}${Math.round(a / 1e4).toLocaleString("ko-KR")}만 원`;
  return `${s}${Math.round(a).toLocaleString("ko-KR")}원`;
}
export const tonnes = (v?: number) => (v === undefined || !Number.isFinite(v) ? "–" : `${num(v)}톤`);
