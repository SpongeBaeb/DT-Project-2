// 배 한 척의 판정: 화면마다 같은 규칙으로 한 단어 결론을 붙인다.
// 순서가 중요하다. 보고 값이 의심되면 다른 숫자를 믿을 수 없으므로 먼저 본다.
import type { Ship } from "./data";
import { isHigh, vsPeer } from "./data";

export type VerdictKey = "check" | "berth" | "real" | "year" | "good" | "same";

export const VERDICT: Record<VerdictKey, { name: string; line: string }> = {
  check: { name: "데이터 확인 필요", line: "보고값에 이상한 점이 있어 비교 결과를 그대로 믿기 어려움" },
  berth: { name: "정박 요인", line: "등급을 끌어내린 것은 항해가 아니라 항구에서 쓴 연료" },
  real: { name: "지속 초과", line: "같은 조건의 배보다 여러 해 꾸준히 연료를 더 씀 (위치 z ≥ 2)" },
  year: { name: "단년 초과", line: "올해는 동급보다 더 썼지만, 여러 해로 보면 꾸준하다고 보기 어려움" },
  good: { name: "동급 대비 우수", line: "같은 급 배보다 바다 위에서 연료를 10% 이상 덜 씀" },
  same: { name: "동급 수준", line: "같은 급 배와 차이 10% 이내" },
};

export function verdictOf(s: Ship): VerdictKey {
  const sig = s.sig ?? [];
  if (sig.includes("report") || sig.includes("fuel") || sig.includes("special")) return "check";
  if (sig.includes("berth")) return "berth";
  if (sig.includes("short")) return "check";
  if (isHigh(s)) return "real";
  const v = vsPeer(s);
  if (v > 10) return "year";
  if (v < -10) return "good";
  return "same";
}
