/**
 * Canvas rendering: pose skeleton, landmark dots and garment sprites.
 *
 * The overlay canvas is sized to the video's intrinsic resolution and stretched
 * with CSS, so all drawing happens in video pixel space. Mirroring is a CSS
 * transform on both <video> and <canvas>, which keeps this math mirror-free.
 */
import type { Placement } from './anchors';
import type { Landmark, OverlayConfig } from './types';

/** BlazePose skeleton edges, grouped so each limb can get its own hue. */
const CONNECTIONS: [number, number][] = [
  // face
  [0, 1], [1, 2], [2, 3], [3, 7], [0, 4], [4, 5], [5, 6], [6, 8], [9, 10],
  // torso
  [11, 12], [11, 23], [12, 24], [23, 24],
  // arms
  [11, 13], [13, 15], [15, 17], [15, 19], [15, 21], [17, 19],
  [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
  // legs
  [23, 25], [25, 27], [27, 29], [27, 31], [29, 31],
  [24, 26], [26, 28], [28, 30], [28, 32], [30, 32],
];

const ACCENT = '#0a84ff';
const ACCENT_SOFT = 'rgba(64, 156, 255, 0.85)';
const JOINT = '#30d158';

export function clear(ctx: CanvasRenderingContext2D): void {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
}

export function drawSkeleton(
  ctx: CanvasRenderingContext2D,
  landmarks: Landmark[],
  width: number,
  height: number,
  opts: { lines?: boolean; dots?: boolean; visibilityThreshold?: number } = {},
): void {
  const { lines = true, dots = true, visibilityThreshold = 0.5 } = opts;
  const visible = (i: number) =>
    landmarks[i] && (landmarks[i].visibility ?? 1) >= visibilityThreshold;
  const scale = Math.max(width, height) / 720;

  if (lines) {
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineWidth = Math.max(2, 3 * scale);
    ctx.strokeStyle = ACCENT_SOFT;
    ctx.shadowColor = ACCENT;
    ctx.shadowBlur = 10 * scale;
    ctx.beginPath();
    for (const [a, b] of CONNECTIONS) {
      if (!visible(a) || !visible(b)) continue;
      ctx.moveTo(landmarks[a].x * width, landmarks[a].y * height);
      ctx.lineTo(landmarks[b].x * width, landmarks[b].y * height);
    }
    ctx.stroke();
    ctx.restore();
  }

  if (dots) {
    ctx.save();
    ctx.fillStyle = JOINT;
    const r = Math.max(2.5, 4 * scale);
    for (let i = 0; i < landmarks.length; i += 1) {
      if (!visible(i)) continue;
      ctx.beginPath();
      ctx.arc(landmarks[i].x * width, landmarks[i].y * height, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
}

/** Draw one garment sprite for each solved placement. */
export function drawGarment(
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource & { width: number; height: number },
  placements: Placement[],
  cfg: OverlayConfig,
): void {
  if (!image.width || !image.height) return;
  const aspect = image.height / image.width;

  for (const p of placements) {
    const w = p.width;
    const h = w * aspect;
    ctx.save();
    ctx.globalAlpha = Math.min(Math.max(cfg.opacity, 0), 1);
    ctx.translate(p.cx, p.cy);
    ctx.rotate(p.angle);
    // Flip first, rotate second (the canvas applies transforms innermost-first),
    // matching the Pillow implementation on the backend.
    if (p.mirror) ctx.scale(-1, 1);
    ctx.drawImage(image, -w * cfg.pivot_x, -h * cfg.pivot_y, w, h);
    ctx.restore();
  }
}

/** Small translucent HUD in the corner of the stage. */
export function drawHud(
  ctx: CanvasRenderingContext2D,
  lines: string[],
  width: number,
  height: number,
): void {
  if (!lines.length) return;
  const scale = Math.max(width, height) / 720;
  const pad = 12 * scale;
  const fontSize = 14 * scale;
  ctx.save();
  ctx.font = `${fontSize}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  const textWidth = Math.max(...lines.map((l) => ctx.measureText(l).width));
  const boxW = textWidth + pad * 2;
  const boxH = lines.length * fontSize * 1.45 + pad * 1.4;
  ctx.fillStyle = 'rgba(8, 8, 10, 0.55)';
  ctx.beginPath();
  ctx.roundRect(pad, pad, boxW, boxH, 10 * scale);
  ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  lines.forEach((line, i) => {
    ctx.fillText(line, pad * 2, pad * 1.9 + fontSize * (i + 0.8));
  });
  ctx.restore();
}

/**
 * Compose the current frame + overlays into an offscreen canvas.
 * Used for snapshots and for handing a frame to a Phase 2 engine.
 */
export function captureFrame(
  video: HTMLVideoElement,
  overlay: HTMLCanvasElement,
  mirror: boolean,
  includeOverlay = true,
): HTMLCanvasElement {
  const out = document.createElement('canvas');
  out.width = video.videoWidth || overlay.width;
  out.height = video.videoHeight || overlay.height;
  const ctx = out.getContext('2d');
  if (!ctx) return out;
  ctx.save();
  if (mirror) {
    ctx.translate(out.width, 0);
    ctx.scale(-1, 1);
  }
  ctx.drawImage(video, 0, 0, out.width, out.height);
  if (includeOverlay) ctx.drawImage(overlay, 0, 0, out.width, out.height);
  ctx.restore();
  return out;
}
