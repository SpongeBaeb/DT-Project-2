// 선종별 측면 렌더링 (SVG). 선체 남색 + 수면 아래 적색 선저 도료 + 선종별 화물 구역.
import { useId } from "react";

const BOX = ["#2b6f8a", "#b5382c", "#b07d1f", "#5f7d6b", "#3d5a73", "#8a9aa8", "#c9b37e", "#6d5c8a"];
const W = 640;
const DECK = 112; // 갑판 높이
const WL = 146; // 수선
const KEEL = 170;

type Kind = "container" | "bulk" | "tanker" | "chemical" | "lng" | "lpg" | "pctc" | "general" | "passenger" | "other";

export function kindOf(type: string): Kind {
  switch (type) {
    case "container": case "container_ro_ro": return "container";
    case "bulk": return "bulk";
    case "tanker": return "tanker";
    case "chemical_tanker": return "chemical";
    case "lng_carrier": return "lng";
    case "gas_carrier": return "lpg";
    case "vehicle_carrier": case "ro_ro": return "pctc";
    case "general_cargo": case "reefer": return "general";
    case "cruise": case "ro_pax": return "passenger";
    default: return "other";
  }
}

function rand(seed: number) {
  let s = seed;
  return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
}

export default function ShipArt({ type, seed = 7, water = true, className }: { type: string; seed?: number; water?: boolean; className?: string }) {
  const uid = useId().replace(/:/g, "");
  const k = kindOf(type);
  const r = rand(seed);
  const tall = k === "pctc" || k === "passenger";
  const hullPath = `M28,${DECK} L590,${DECK} C604,${DECK} 616,${DECK - 4} 622,${DECK - 8} L606,${KEEL - 8} C602,${KEEL} 596,${KEEL} 588,${KEEL} L70,${KEEL} C46,${KEEL} 34,${KEEL - 10} 30,${WL} Z`;
  const parts: JSX.Element[] = [];

  // 선미 상부 구조 (거주구·선교·연돌)
  const accom = (x: number, h: number) => (
    <g key="accom">
      <rect x={x + 10} y={DECK - h - 22} width={18} height={24} rx={2} fill={`url(#${uid}fun)`} />
      <rect x={x + 10} y={DECK - h - 18} width={18} height={4} fill="#b5382c" />
      <rect x={x} y={DECK - h} width={62} height={h} rx={3} fill={`url(#${uid}sup)`} stroke="#c3ccd4" strokeWidth={0.8} />
      {Array.from({ length: Math.floor(h / 11) }).map((_, i) => (
        <rect key={i} x={x + 6} y={DECK - h + 6 + i * 11} width={50} height={3.5} rx={1} fill="#24394d" opacity={i === 0 ? 0.95 : 0.55} />
      ))}
      <rect x={x - 6} y={DECK - h} width={74} height={4} rx={1} fill="#e9eef2" stroke="#c3ccd4" strokeWidth={0.6} />
    </g>
  );

  if (k === "container") {
    for (let i = 0; i < 16; i++) {
      const x = 148 + i * 27;
      const tiers = i === 0 || i === 15 ? 2 : 3 + Math.floor(r() * 3);
      for (let j = 0; j < tiers; j++) {
        parts.push(<rect key={`c${i}-${j}`} x={x} y={DECK - 12 * (j + 1)} width={25} height={11} rx={1} fill={BOX[Math.floor(r() * BOX.length)]} />);
        parts.push(<rect key={`l${i}-${j}`} x={x} y={DECK - 12 * (j + 1)} width={25} height={2} fill="#ffffff" opacity={0.18} />);
      }
    }
    parts.push(accom(66, 58));
  } else if (k === "bulk") {
    for (let i = 0; i < 7; i++) {
      parts.push(<rect key={`h${i}`} x={150 + i * 60} y={DECK - 12} width={46} height={12} rx={3} fill={`url(#${uid}hatch)`} stroke="#8592a0" strokeWidth={0.8} />);
    }
    parts.push(accom(66, 46));
  } else if (k === "tanker" || k === "chemical") {
    parts.push(<rect key="pipe" x={130} y={DECK - 7} width={450} height={3} rx={1.5} fill="#8592a0" />);
    parts.push(<rect key="walk" x={130} y={DECK - 14} width={450} height={1.6} fill="#9aa6b1" />);
    for (let i = 0; i < 15; i++) parts.push(<rect key={`p${i}`} x={136 + i * 30} y={DECK - 14} width={1.6} height={14} fill="#9aa6b1" />);
    parts.push(<rect key="mani" x={330} y={DECK - 20} width={22} height={20} rx={2} fill="#9aa6b1" />);
    parts.push(<path key="crane" d={`M341,${DECK - 20} L341,${DECK - 40} L372,${DECK - 26}`} stroke="#5d6b78" strokeWidth={2.4} fill="none" />);
    if (k === "chemical") for (let i = 0; i < 7; i++) parts.push(<rect key={`t${i}`} x={150 + i * 62} y={DECK - 12} width={20} height={9} rx={4.5} fill="#d6b56a" stroke="#8592a0" strokeWidth={0.6} />);
    parts.push(accom(66, 46));
  } else if (k === "lng") {
    for (let i = 0; i < 4; i++) {
      const cx = 200 + i * 98;
      parts.push(<path key={`d${i}`} d={`M${cx - 44},${DECK} A44,44 0 0 1 ${cx + 44},${DECK} Z`} fill={`url(#${uid}dome)`} stroke="#b9c3cc" strokeWidth={0.8} />);
      parts.push(<rect key={`b${i}`} x={cx - 46} y={DECK - 4} width={92} height={4} fill="#2b6f8a" />);
    }
    parts.push(accom(66, 52));
  } else if (k === "lpg") {
    for (let i = 0; i < 4; i++) parts.push(<rect key={`g${i}`} x={150 + i * 104} y={DECK - 22} width={92} height={22} rx={11} fill={`url(#${uid}dome)`} stroke="#b9c3cc" strokeWidth={0.8} />);
    parts.push(<rect key="pipe" x={150} y={DECK - 26} width={410} height={2} fill="#8592a0" />);
    parts.push(accom(66, 50));
  } else if (k === "pctc") {
    parts.push(<path key="box" d={`M40,${DECK} L40,${DECK - 74} C40,${DECK - 78} 44,${DECK - 80} 48,${DECK - 80} L560,${DECK - 80} C590,${DECK - 80} 606,${DECK - 50} 610,${DECK - 8} L610,${DECK} Z`} fill={`url(#${uid}sup)`} stroke="#c3ccd4" strokeWidth={0.8} />);
    parts.push(<rect key="stripe" x={40} y={DECK - 22} width={566} height={5} fill="#1c3550" />);
    parts.push(<rect key="br" x={520} y={DECK - 92} width={64} height={12} rx={2} fill={`url(#${uid}sup)`} stroke="#c3ccd4" strokeWidth={0.8} />);
    parts.push(<rect key="brw" x={526} y={DECK - 88} width={52} height={3.5} fill="#24394d" />);
    parts.push(<rect key="fun" x={80} y={DECK - 92} width={22} height={12} rx={2} fill={`url(#${uid}fun)`} />);
  } else if (k === "general") {
    for (let i = 0; i < 4; i++) parts.push(<rect key={`h${i}`} x={170 + i * 100} y={DECK - 10} width={70} height={10} rx={3} fill={`url(#${uid}hatch)`} stroke="#8592a0" strokeWidth={0.8} />);
    for (const x of [255, 455]) {
      parts.push(<rect key={`ped${x}`} x={x - 5} y={DECK - 34} width={10} height={34} fill="#b07d1f" />);
      parts.push(<path key={`jib${x}`} d={`M${x},${DECK - 32} L${x + 62},${DECK - 58}`} stroke="#b07d1f" strokeWidth={4} strokeLinecap="round" />);
      parts.push(<path key={`w${x}`} d={`M${x + 60},${DECK - 57} L${x + 60},${DECK - 26}`} stroke="#5d6b78" strokeWidth={1} />);
    }
    parts.push(accom(66, 44));
  } else if (k === "passenger") {
    const decks = [[60, 560, 26], [96, 520, 22], [140, 470, 20], [190, 400, 18]];
    let y = DECK;
    decks.forEach(([x0, x1, h], i) => {
      y -= h;
      parts.push(<rect key={`dk${i}`} x={x0} y={y} width={x1 - x0} height={h} rx={4} fill={`url(#${uid}sup)`} stroke="#c3ccd4" strokeWidth={0.8} />);
      parts.push(<rect key={`wn${i}`} x={x0 + 8} y={y + h / 2 - 2} width={x1 - x0 - 16} height={4} rx={2} fill="#24394d" opacity={0.75} />);
    });
    parts.push(<path key="fun" d={`M250,${y} L256,${y - 26} L290,${y - 26} L296,${y} Z`} fill={`url(#${uid}fun)`} />);
    parts.push(<rect key="funb" x={254} y={y - 20} width={38} height={5} fill="#b5382c" />);
  } else {
    for (let i = 0; i < 5; i++) parts.push(<rect key={`o${i}`} x={170 + i * 80} y={DECK - 14} width={56} height={14} rx={2} fill={`url(#${uid}hatch)`} stroke="#8592a0" strokeWidth={0.8} />);
    parts.push(accom(66, 48));
  }

  return (
    <svg viewBox={`0 0 ${W} ${water ? 200 : 180}`} className={className} role="img" aria-label={`${type} 측면도`}>
      <defs>
        <linearGradient id={`${uid}hull`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2a4a68" />
          <stop offset="0.55" stopColor="#15304a" />
          <stop offset="1" stopColor="#0d2032" />
        </linearGradient>
        <linearGradient id={`${uid}af`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c0473a" />
          <stop offset="1" stopColor="#7d241c" />
        </linearGradient>
        <linearGradient id={`${uid}sup`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#dde4ea" />
        </linearGradient>
        <linearGradient id={`${uid}hatch`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#b8c2cc" />
          <stop offset="1" stopColor="#8e9aa6" />
        </linearGradient>
        <radialGradient id={`${uid}dome`} cx="0.35" cy="0.2" r="0.9">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#d5dde4" />
        </radialGradient>
        <linearGradient id={`${uid}fun`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#3d5a73" />
          <stop offset="1" stopColor="#1c3550" />
        </linearGradient>
        <linearGradient id={`${uid}sea`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2b6f8a" stopOpacity="0.32" />
          <stop offset="1" stopColor="#2b6f8a" stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${uid}below`}>
          <rect x="0" y={WL} width={W} height={60} />
        </clipPath>
      </defs>
      {parts}
      <path d={hullPath} fill={`url(#${uid}hull)`} />
      <path d={hullPath} fill={`url(#${uid}af)`} clipPath={`url(#${uid}below)`} />
      <path d={`M28,${DECK + 1.5} L590,${DECK + 1.5} C604,${DECK + 1.5} 616,${DECK - 2.5} 621,${DECK - 6.5}`} stroke="#ffffff" strokeOpacity={0.35} strokeWidth={1.4} fill="none" />
      <rect x={30} y={WL - 1.2} width={584} height={2.4} fill="#e9eef2" opacity={0.9} />
      {water && (
        <g>
          <rect x={0} y={WL + 4} width={W} height={56} fill={`url(#${uid}sea)`} />
          <path d={`M0,${WL + 4} ${Array.from({ length: 16 }).map(() => "q20,-3 40,0").join(" ")}`} stroke="#2b6f8a" strokeOpacity={0.55} strokeWidth={1.4} fill="none" />
        </g>
      )}
    </svg>
  );
}
