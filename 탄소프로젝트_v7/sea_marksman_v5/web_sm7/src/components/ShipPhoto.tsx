// 선종별 선박 사진 (팀 공유 13종 투명 PNG → public/ships/<선종>.webp). 해당 선종 사진이 없으면 일러스트로 대신한다.
import ShipArt from "./ShipArt";

export const SHIP_PHOTO_TYPES = new Set(["bulk", "tanker", "chemical_tanker", "general_cargo", "vehicle_carrier", "lng_carrier", "gas_carrier", "ro_pax", "ro_ro", "reefer", "cruise", "container_ro_ro", "container"]);

export default function ShipPhoto({ type, seed = 0, small, className = "", alt = "" }: { type: string; seed?: number; small?: boolean; className?: string; alt?: string }) {
  if (!SHIP_PHOTO_TYPES.has(type)) return <ShipArt type={type} seed={seed} water={false} className={className} />;
  return <img className={`ship-photo ${className}`} src={`${import.meta.env.BASE_URL}ships/${type}${small ? "-sm" : ""}.webp`} alt={alt} loading={small ? "lazy" : "eager"} decoding="async" />;
}
