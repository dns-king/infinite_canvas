export type Biome = "forest" | "desert" | "ocean" | "alien";

export interface TileRequest {
  x: number;
  y: number;
  seed: number;
  biome: Biome;
  prompt?: string | null;
  lod: 256 | 512;
}

export interface TilePayload extends TileRequest {
  requestId: string;
  dataUrl: string;
  meta: {
    cached: boolean;
    latency_ms: number;
  };
}

export interface TileStateSnapshot {
  center: [number, number];
  loaded: Set<string>;
  pending: Set<string>;
}

