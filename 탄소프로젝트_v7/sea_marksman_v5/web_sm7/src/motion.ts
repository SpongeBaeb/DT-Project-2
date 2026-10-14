// 스크롤 연출 공용: 부드러운 스크롤(Lenis) + GSAP ScrollTrigger. 움직임 줄이기 설정이면 둘 다 쓰지 않는다.
import { useEffect, useLayoutEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";

gsap.registerPlugin(ScrollTrigger);
export { gsap, ScrollTrigger };

export const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let lenis: Lenis | null = null;
let raf = 0;

/** 소개 화면에서만 부드러운 스크롤을 켠다 */
export function useSmoothScroll(on: boolean) {
  useEffect(() => {
    if (!on || reduced()) return;
    lenis = new Lenis({ duration: 1.15, smoothWheel: true });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (t: number) => { lenis?.raf(t); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); lenis?.destroy(); lenis = null; };
  }, [on]);
}

export const scrollTop = () => { if (lenis) lenis.scrollTo(0, { immediate: true }); else window.scrollTo(0, 0); };

/** gsap.context 를 컴포넌트 수명에 묶는다 */
export function useGsap(scope: React.RefObject<HTMLElement>, fn: () => void, deps: unknown[] = []) {
  useLayoutEffect(() => {
    if (!scope.current) return;
    const ctx = gsap.context(fn, scope);
    // 이미지·글꼴이 늦게 들어와 높이가 바뀌면 위치를 다시 잰다
    const t = window.setTimeout(() => ScrollTrigger.refresh(), 400);
    return () => { window.clearTimeout(t); ctx.revert(); };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
