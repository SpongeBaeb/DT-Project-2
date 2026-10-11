/**
 * 화면이 쓰는 타입. 직접 정의하지 않고 Python 약속(contracts/api.py)에서 자동 생성된 schema.d.ts 를 다시 내보낸다.
 * 약속이 바뀌면:  uv run python tasks.py schema   → schema.d.ts 갱신 → 타입 오류가 바뀐 곳을 알려 줌
 */
import type { components } from "./schema";

type S = components["schemas"];
export type DiagnosisResult = S["DiagnosisResult"];
export type DiagnoseRequest = S["DiagnoseRequest"];
export type ShipInputs = S["ShipInputs"];
export type ShipFile = S["ShipFile"];
export type IndexEntry = S["IndexEntry"];
export type Meta = S["Meta"];
export type WhatIfSpeedRequest = S["WhatIfSpeedRequest"];
export type WhatIfSpeedResponse = S["WhatIfSpeedResponse"];
