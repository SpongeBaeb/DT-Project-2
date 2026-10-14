// 주소(해시 라우팅)와 사용자가 넣은 가격. 가격은 이 브라우저에만 저장한다(입력값은 서버에 보내지 않음).
import { useEffect, useState, useSyncExternalStore } from "react";
import type { Prices } from "./calc";

export function useRoute() {
  const read = () => {
    const h = window.location.hash.replace(/^#/, "") || "/";
    const [path, q = ""] = h.split("?");
    return { path, query: new URLSearchParams(q) };
  };
  const [r, setR] = useState(read);
  useEffect(() => {
    const f = () => { setR(read()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}
export const go = (to: string) => { window.location.hash = to; };

const KEY = "sm.prices.v1";
let prices: Prices = (() => { try { return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Prices; } catch { return {}; } })();
const subs = new Set<() => void>();
export function setPrices(p: Prices) {
  prices = p;
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* 저장 실패는 무시: 이번 화면에서만 쓴다 */ }
  subs.forEach((f) => f());
}
export const usePrices = () => useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => prices);

export function downloadCsv(name: string, rows: (string | number | undefined | null)[][]) {
  const esc = (v: string | number | undefined | null) => (v === undefined || v === null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const blob = new Blob(["\ufeff" + rows.map((r) => r.map(esc).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── 비교 목록(최대 4척)과 관심 목록(메모 포함). 이 브라우저에만 저장한다 ──
function listStore<T>(key: string, init: T) {
  let v: T = (() => { try { const s = localStorage.getItem(key); return s ? (JSON.parse(s) as T) : init; } catch { return init; } })();
  const ss = new Set<() => void>();
  return {
    get: () => v,
    set: (n: T) => { v = n; try { localStorage.setItem(key, JSON.stringify(n)); } catch { /* 저장 실패는 무시 */ } ss.forEach((f) => f()); },
    use: () => useSyncExternalStore((f) => (ss.add(f), () => ss.delete(f)), () => v),
  };
}
export const COMPARE_MAX = 4;
const compare = listStore<number[]>("sm.compare.v1", []);
export const useCompare = compare.use;
export function toggleCompare(imo: number): boolean {
  const c = compare.get();
  if (c.includes(imo)) { compare.set(c.filter((x) => x !== imo)); return true; }
  if (c.length >= COMPARE_MAX) return false;
  compare.set([...c, imo]);
  return true;
}
export const clearCompare = () => compare.set([]);

export interface WatchItem { imo: number; memo: string; added: string }
const watch = listStore<WatchItem[]>("sm.watch.v1", []);
export const useWatch = watch.use;
export const toggleWatch = (imo: number) => {
  const w = watch.get();
  watch.set(w.some((x) => x.imo === imo) ? w.filter((x) => x.imo !== imo) : [...w, { imo, memo: "", added: new Date().toISOString().slice(0, 10) }]);
};
export const setMemo = (imo: number, memo: string) => watch.set(watch.get().map((x) => (x.imo === imo ? { ...x, memo } : x)));

// ── 화면 테마 (라이트·다크) ──
const theme = listStore<"light" | "dark">("sm.theme.v7", "dark");
export const useTheme = theme.use;
export const setTheme = theme.set;
