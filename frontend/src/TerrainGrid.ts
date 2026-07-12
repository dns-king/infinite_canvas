import * as THREE from "three";
import { makeFallbackDataUrl } from "./fallbackTexture";
import { TileClient } from "./tileClient";
import type { Biome, TileStateSnapshot } from "./types";

type TileEntry = {
  mesh: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>;
  coord: string | null;
  texture: THREE.Texture | null;
  loadingTexture: THREE.Texture;
};

export class TerrainGrid {
  readonly loaded = new Set<string>();
  readonly pending = new Set<string>();
  private readonly entries: TileEntry[] = [];
  private readonly byCoord = new Map<string, TileEntry>();
  private readonly textureLoader = new THREE.TextureLoader();
  private center: [number, number] = [Number.NaN, Number.NaN];
  private biomeVersion = 0;
  private lastBiome: Biome = "forest";

  constructor(
    scene: THREE.Scene,
    private readonly client: TileClient,
    private readonly renderer: THREE.WebGLRenderer,
    private readonly tileWorldSize = 32,
    private readonly radius = 3,
  ) {
    const geometry = new THREE.PlaneGeometry(tileWorldSize, tileWorldSize, 80, 80);
    geometry.rotateX(-Math.PI / 2);

    for (let i = 0; i < (radius * 2 + 1) ** 2; i += 1) {
      const loadingTexture = this.makeLoadingTexture();
      const material = new THREE.MeshStandardMaterial({
        map: loadingTexture,
        roughness: 0.9,
        metalness: 0.03,
        bumpScale: 2.4,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.frustumCulled = false;
      mesh.receiveShadow = true;
      scene.add(mesh);
      this.entries.push({ mesh, coord: null, texture: material.map, loadingTexture });
    }
  }

  update(camera: THREE.Camera, velocity: THREE.Vector3, seed: number, biome: Biome): TileStateSnapshot {
    const nextCenter: [number, number] = [
      Math.floor(camera.position.x / this.tileWorldSize),
      Math.floor(camera.position.z / this.tileWorldSize),
    ];

    if (biome !== this.lastBiome) {
      this.lastBiome = biome;
      this.biomeVersion += 1;
      this.loaded.clear();
      this.pending.clear();
      for (const entry of this.entries) {
        this.releaseEntry(entry);
      }
      this.byCoord.clear();
    }

    if (nextCenter[0] !== this.center[0] || nextCenter[1] !== this.center[1] || this.byCoord.size === 0) {
      this.center = nextCenter;
      this.assignVisibleTiles(seed, biome);
    }

    const speed = velocity.length();
    if (speed > 0.2) {
      this.client.prefetch(
        camera.position.x,
        camera.position.z,
        velocity.x,
        velocity.z,
        seed,
        biome,
        this.radius,
      );
    }

    return {
      center: this.center,
      loaded: new Set(this.loaded),
      pending: new Set(this.pending),
    };
  }

  private assignVisibleTiles(seed: number, biome: Biome): void {
    const visible = this.visibleCoords();
    const visibleKeys = new Set(visible.map(([x, y]) => keyOf(x, y)));

    for (const [key, entry] of this.byCoord) {
      if (!visibleKeys.has(key)) {
        this.byCoord.delete(key);
        this.loaded.delete(key);
        this.pending.delete(key);
        this.releaseEntry(entry);
      }
    }

    for (const [x, y, distance] of visible) {
      const key = keyOf(x, y);
      if (this.byCoord.has(key)) {
        continue;
      }
      const entry = this.entries.find((candidate) => candidate.coord === null);
      if (!entry) {
        continue;
      }
      this.assignEntry(entry, x, y, distance, seed, biome);
    }
  }

  private visibleCoords(): Array<[number, number, number]> {
    const coords: Array<[number, number, number]> = [];
    const [cx, cy] = this.center;
    for (let y = cy - this.radius; y <= cy + this.radius; y += 1) {
      for (let x = cx - this.radius; x <= cx + this.radius; x += 1) {
        coords.push([x, y, Math.abs(x - cx) + Math.abs(y - cy)]);
      }
    }
    coords.sort((a, b) => a[2] - b[2]);
    return coords;
  }

  private assignEntry(entry: TileEntry, x: number, y: number, distance: number, seed: number, biome: Biome): void {
    const key = keyOf(x, y);
    const version = this.biomeVersion;
    entry.coord = key;
    entry.mesh.visible = true;
    entry.mesh.position.set((x + 0.5) * this.tileWorldSize, 0, (y + 0.5) * this.tileWorldSize);
    if (entry.texture && entry.texture !== entry.loadingTexture) {
      entry.texture.dispose();
    }
    entry.texture = entry.loadingTexture;
    entry.mesh.material.map = entry.loadingTexture;
    entry.mesh.material.bumpMap = null;
    entry.mesh.material.needsUpdate = true;
    this.byCoord.set(key, entry);
    this.pending.add(key);
    this.applyTexture(entry, makeFallbackDataUrl(x, y, seed, biome, 256));

    const lod: 256 | 512 = distance > 2 ? 256 : 512;
    this.client
      .requestTile({ x, y, seed, biome, lod })
      .then((payload) => {
        if (entry.coord !== key || version !== this.biomeVersion) {
          return;
        }
        this.applyTexture(entry, payload.dataUrl);
        this.pending.delete(key);
        this.loaded.add(key);
      })
      .catch(() => {
        if (entry.coord !== key || version !== this.biomeVersion) {
          return;
        }
        this.applyTexture(entry, makeFallbackDataUrl(x, y, seed, biome));
        this.pending.delete(key);
        this.loaded.add(key);
      });
  }

  private releaseEntry(entry: TileEntry): void {
    entry.coord = null;
    entry.mesh.visible = false;
  }

  private applyTexture(entry: TileEntry, dataUrl: string): void {
    this.textureLoader.load(dataUrl, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
      texture.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
      texture.needsUpdate = true;
      if (entry.texture && entry.texture !== entry.loadingTexture) {
        entry.texture.dispose();
      }
      entry.texture = texture;
      entry.mesh.material.map = texture;
      entry.mesh.material.bumpMap = texture;
      entry.mesh.material.needsUpdate = true;
    });
  }

  private makeLoadingTexture(): THREE.Texture {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.fillStyle = "#161a16";
      ctx.fillRect(0, 0, 128, 128);
      ctx.fillStyle = "#2b3328";
      for (let y = 0; y < 128; y += 16) {
        for (let x = 0; x < 128; x += 16) {
          if ((x + y) % 32 === 0) {
            ctx.fillRect(x, y, 16, 16);
          }
        }
      }
      ctx.strokeStyle = "#d9ae5b";
      ctx.lineWidth = 2;
      ctx.strokeRect(1, 1, 126, 126);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }
}

function keyOf(x: number, y: number): string {
  return `${x},${y}`;
}
