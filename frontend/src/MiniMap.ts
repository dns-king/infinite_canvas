import type { TileStateSnapshot } from "./types";

export class MiniMap {
  private readonly ctx: CanvasRenderingContext2D;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Could not initialize minimap");
    }
    this.ctx = ctx;
  }

  draw(snapshot: TileStateSnapshot): void {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#101411";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const cell = 14;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const [centerX, centerY] = snapshot.center;

    ctx.strokeStyle = "rgba(230, 220, 180, 0.15)";
    ctx.lineWidth = 1;
    for (let i = -6; i <= 6; i += 1) {
      ctx.beginPath();
      ctx.moveTo(cx + i * cell, 0);
      ctx.lineTo(cx + i * cell, canvas.height);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, cy + i * cell);
      ctx.lineTo(canvas.width, cy + i * cell);
      ctx.stroke();
    }

    for (const key of snapshot.loaded) {
      this.paintTile(key, centerX, centerY, cell, "rgba(91, 196, 135, 0.86)");
    }
    for (const key of snapshot.pending) {
      this.paintTile(key, centerX, centerY, cell, "rgba(226, 179, 86, 0.86)");
    }

    ctx.fillStyle = "#f6eee0";
    ctx.fillRect(cx - 4, cy - 4, 8, 8);
  }

  private paintTile(key: string, centerX: number, centerY: number, cell: number, fill: string): void {
    const [x, y] = key.split(",").map(Number);
    const px = this.canvas.width / 2 + (x - centerX) * cell;
    const py = this.canvas.height / 2 + (y - centerY) * cell;
    if (px < -cell || py < -cell || px > this.canvas.width + cell || py > this.canvas.height + cell) {
      return;
    }
    this.ctx.fillStyle = fill;
    this.ctx.fillRect(px - cell / 2 + 1, py - cell / 2 + 1, cell - 2, cell - 2);
  }
}

