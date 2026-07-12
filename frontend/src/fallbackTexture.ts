import type { Biome } from "./types";

const palettes: Record<Biome, string[]> = {
  forest: ["#17372d", "#2d6740", "#6f8749", "#d5ca95"],
  desert: ["#4d362f", "#9b663f", "#d49b5e", "#f0d79c"],
  ocean: ["#06224a", "#07527f", "#1395a3", "#ded39d"],
  alien: ["#211736", "#52357e", "#23929b", "#bcd77a"],
};

export function makeFallbackDataUrl(x: number, y: number, seed: number, biome: Biome, size = 512): string {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return "";
  }

  const palette = palettes[biome];
  const image = ctx.createImageData(size, size);
  const data = image.data;
  let i = 0;
  for (let py = 0; py < size; py += 1) {
    for (let px = 0; px < size; px += 1) {
      const wx = x * size + px;
      const wy = y * size + py;
      const n =
        noise(wx, wy, seed, 384) * 0.48 +
        noise(wx + 1000, wy - 500, seed + 13, 126) * 0.34 +
        noise(wx - 40, wy + 90, seed + 29, 34) * 0.18;
      const color = samplePalette(palette, n);
      data[i++] = color[0];
      data[i++] = color[1];
      data[i++] = color[2];
      data[i++] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

function samplePalette(palette: string[], t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(0.999, t));
  const scaled = clamped * (palette.length - 1);
  const index = Math.floor(scaled);
  const frac = scaled - index;
  const a = hexToRgb(palette[index]);
  const b = hexToRgb(palette[Math.min(index + 1, palette.length - 1)]);
  return [
    Math.round(a[0] * (1 - frac) + b[0] * frac),
    Math.round(a[1] * (1 - frac) + b[1] * frac),
    Math.round(a[2] * (1 - frac) + b[2] * frac),
  ];
}

function hexToRgb(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function noise(x: number, y: number, seed: number, scale: number): number {
  const sx = x / scale;
  const sy = y / scale;
  const x0 = Math.floor(sx);
  const y0 = Math.floor(sy);
  const fx = smooth(sx - x0);
  const fy = smooth(sy - y0);
  const a = hash(x0, y0, seed);
  const b = hash(x0 + 1, y0, seed);
  const c = hash(x0, y0 + 1, seed);
  const d = hash(x0 + 1, y0 + 1, seed);
  return lerp(lerp(a, b, fx), lerp(c, d, fx), fy);
}

function hash(x: number, y: number, seed: number): number {
  let n = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(seed, 1442695041);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
}

function lerp(a: number, b: number, t: number): number {
  return a * (1 - t) + b * t;
}

function smooth(t: number): number {
  return t * t * (3 - 2 * t);
}

