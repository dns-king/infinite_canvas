import type { Biome, TilePayload, TileRequest } from "./types";

type PendingRequest = {
  resolve: (payload: TilePayload) => void;
  reject: (error: Error) => void;
  timer: number;
  request: TileRequest;
};

export class TileClient {
  private socket: WebSocket | null = null;
  private readonly pending = new Map<string, PendingRequest>();
  private reconnectTimer = 0;
  private reconnectDelay = 650;
  private statusCallback: (status: string) => void = () => {};

  constructor(private readonly apiBase = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000") {
    this.connect();
  }

  onStatus(callback: (status: string) => void): void {
    this.statusCallback = callback;
  }

  get connected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  async requestTile(request: TileRequest): Promise<TilePayload> {
    const requestId = `${request.seed}:${request.biome}:${request.lod}:${request.x}:${request.y}:${crypto.randomUUID()}`;
    if (!this.connected) {
      return this.fetchTile(request, requestId);
    }

    return new Promise<TilePayload>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(requestId);
        this.fetchTile(request, requestId).then(resolve).catch(reject);
      }, 45000);
      this.pending.set(requestId, { resolve, reject, timer, request });
      this.socket?.send(JSON.stringify({ type: "tile.request", requestId, ...request }));
    });
  }

  prefetch(
    cameraX: number,
    cameraZ: number,
    velocityX: number,
    velocityZ: number,
    seed: number,
    biome: Biome,
    radius: number,
  ): void {
    if (!this.connected) {
      return;
    }
    this.socket?.send(
      JSON.stringify({
        type: "tile.prefetch",
        cameraX,
        cameraZ,
        velocityX,
        velocityZ,
        seed,
        biome,
        radius,
      }),
    );
  }

  private connect(): void {
    window.clearTimeout(this.reconnectTimer);
    const wsBase = this.apiBase.replace(/^http/, "ws");
    this.socket = new WebSocket(`${wsBase}/ws/tiles`);

    this.socket.addEventListener("open", () => {
      this.reconnectDelay = 650;
      this.statusCallback("Backend connected");
    });

    this.socket.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "tile") {
        const pending = this.pending.get(payload.requestId);
        if (!pending) {
          return;
        }
        window.clearTimeout(pending.timer);
        this.pending.delete(payload.requestId);
        pending.resolve(payload as TilePayload);
      } else if (payload.type === "tile.error") {
        const pending = this.pending.get(payload.requestId);
        if (!pending) {
          return;
        }
        window.clearTimeout(pending.timer);
        this.pending.delete(payload.requestId);
        this.fetchTile(pending.request, payload.requestId).then(pending.resolve).catch(pending.reject);
      }
    });

    this.socket.addEventListener("close", () => this.scheduleReconnect());
    this.socket.addEventListener("error", () => {
      this.statusCallback("Backend reconnecting");
      this.socket?.close();
    });
  }

  private scheduleReconnect(): void {
    this.statusCallback("Backend offline preview");
    this.reconnectTimer = window.setTimeout(() => this.connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(6000, this.reconnectDelay * 1.55);
  }

  private async fetchTile(request: TileRequest, requestId: string): Promise<TilePayload> {
    const response = await fetch(`${this.apiBase}/generate_tile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw new Error(`Tile ${request.x},${request.y} failed: ${response.status}`);
    }
    const blob = await response.blob();
    const dataUrl = await blobToDataUrl(blob);
    return {
      ...request,
      requestId,
      dataUrl,
      meta: {
        cached: response.headers.get("X-InfiniteCanvas-Meta")?.includes('"cached":true') ?? false,
        latency_ms: 0,
      },
    };
  }
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(reader.error ?? new Error("Blob conversion failed")));
    reader.readAsDataURL(blob);
  });
}

