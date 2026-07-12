import * as THREE from "three";
import { FlyControls } from "./FlyControls";
import { MiniMap } from "./MiniMap";
import { TerrainGrid } from "./TerrainGrid";
import { TileClient } from "./tileClient";
import type { Biome } from "./types";
import "./styles.css";

const canvas = requireElement<HTMLCanvasElement>("#world");
const minimapCanvas = requireElement<HTMLCanvasElement>("#minimap");
const statusEl = requireElement<HTMLElement>("#status");
const loadedCountEl = requireElement<HTMLElement>("#loaded-count");
const pendingCountEl = requireElement<HTMLElement>("#pending-count");
const coordReadoutEl = requireElement<HTMLElement>("#coord-readout");

let activeBiome: Biome = "forest";
const seed = 20260710;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0c1210);
scene.fog = new THREE.FogExp2(0x0c1210, 0.0105);

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const camera = new THREE.PerspectiveCamera(67, window.innerWidth / window.innerHeight, 0.1, 900);
const controls = new FlyControls(camera, canvas);
const client = new TileClient();
const terrain = new TerrainGrid(scene, client, renderer);
const minimap = new MiniMap(minimapCanvas);

client.onStatus((status) => {
  statusEl.textContent = status;
});

buildLighting(scene);
buildAtmosphere(scene);
wireBiomeButtons();

const clock = new THREE.Clock();
let lastPrefetch = 0;

function animate(): void {
  requestAnimationFrame(animate);
  const dt = Math.min(0.05, clock.getDelta());
  controls.update(dt);

  const snapshot = terrain.update(camera, controls.velocity, seed, activeBiome);
  const elapsed = clock.elapsedTime;
  if (elapsed - lastPrefetch > 0.85) {
    lastPrefetch = elapsed;
    client.prefetch(
      camera.position.x,
      camera.position.z,
      controls.velocity.x,
      controls.velocity.z,
      seed,
      activeBiome,
      3,
    );
  }

  minimap.draw(snapshot);
  loadedCountEl.textContent = String(snapshot.loaded.size);
  pendingCountEl.textContent = String(snapshot.pending.size);
  coordReadoutEl.textContent = `${snapshot.center[0]},${snapshot.center[1]}`;

  renderer.render(scene, camera);
}

animate();

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8));
  renderer.setSize(window.innerWidth, window.innerHeight);
});

function wireBiomeButtons(): void {
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>("[data-biome]"));
  for (const button of buttons) {
    button.addEventListener("click", () => {
      activeBiome = button.dataset.biome as Biome;
      for (const other of buttons) {
        other.classList.toggle("active", other === button);
      }
    });
  }
}

function buildLighting(target: THREE.Scene): void {
  const hemi = new THREE.HemisphereLight(0xcde8dc, 0x2d1e18, 1.25);
  target.add(hemi);

  const sun = new THREE.DirectionalLight(0xffdf9a, 3.4);
  sun.position.set(-72, 96, -36);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 260;
  sun.shadow.camera.left = -120;
  sun.shadow.camera.right = 120;
  sun.shadow.camera.top = 120;
  sun.shadow.camera.bottom = -120;
  target.add(sun);

  const lowFill = new THREE.DirectionalLight(0x5cc3c7, 0.7);
  lowFill.position.set(90, 18, 80);
  target.add(lowFill);
}

function buildAtmosphere(target: THREE.Scene): void {
  const geometry = new THREE.SphereGeometry(460, 48, 24);
  const material = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      topColor: { value: new THREE.Color(0x243a36) },
      bottomColor: { value: new THREE.Color(0x0c1210) },
    },
    vertexShader: `
      varying vec3 vWorldPosition;
      void main() {
        vec4 worldPosition = modelMatrix * vec4(position, 1.0);
        vWorldPosition = worldPosition.xyz;
        gl_Position = projectionMatrix * viewMatrix * worldPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vWorldPosition;
      uniform vec3 topColor;
      uniform vec3 bottomColor;
      void main() {
        float h = normalize(vWorldPosition).y * 0.5 + 0.5;
        vec3 color = mix(bottomColor, topColor, smoothstep(0.05, 0.95, h));
        gl_FragColor = vec4(color, 1.0);
      }
    `,
  });
  const sky = new THREE.Mesh(geometry, material);
  target.add(sky);
}

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) {
    throw new Error(`Missing required element ${selector}`);
  }
  return element;
}
