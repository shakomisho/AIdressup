/**
 * Canvas rendering: pose skeleton, landmark dots and garment sprites.
 *
 * The overlay canvas is sized to the video's intrinsic resolution and stretched
 * with CSS, so all drawing happens in video pixel space. Mirroring is a CSS
 * transform on both <video> and <canvas>, which keeps this math mirror-free.
 */
import type { Placement } from './anchors';
import type { SceneLight } from './lighting';
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

/**
 * Draw one garment sprite for each solved placement.
 *
 * `brightness` shades the sprite toward the room's light level. It is a filter
 * on the draw rather than a post-pass so it only touches this garment — a hat
 * and a shirt can be lit differently once per-part lighting exists.
 */
export function drawGarment(
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource & { width: number; height: number },
  placements: Placement[],
  cfg: OverlayConfig,
  brightness = 1,
): void {
  if (!image.width || !image.height) return;
  const aspect = image.height / image.width;

  for (const p of placements) {
    const w = p.width;
    const h = w * aspect;
    ctx.save();
    ctx.globalAlpha = Math.min(Math.max(cfg.opacity, 0), 1);
    if (brightness !== 1) ctx.filter = `brightness(${brightness.toFixed(3)})`;
    ctx.translate(p.cx, p.cy);
    ctx.rotate(p.angle);
    // Flip first, rotate second (the canvas applies transforms innermost-first),
    // matching the Pillow implementation on the backend.
    if (p.mirror) ctx.scale(-1, 1);
    ctx.drawImage(image, -w * cfg.pivot_x, -h * cfg.pivot_y, w, h);
    ctx.restore();
  }
}

/**
 * Offscreen buffer every garment is drawn into before it reaches the screen.
 *
 * Going through a layer is what makes the two realism passes possible: a tint
 * has to apply to the finished sprite rather than to each `drawImage`, and the
 * silhouette clip has to mask all worn garments as one shape — masking them
 * individually would let a jacket clip against a shirt's edge.
 *
 * Canvases are reused across frames; allocating two per frame at 30 FPS churns
 * the GC badly enough to show up as jitter.
 */
export class GarmentLayer {
  private readonly layer = document.createElement('canvas');
  private readonly maskCanvas = document.createElement('canvas');
  private maskImage: ImageData | null = null;

  /** Clear and resize the buffer. Returns the context to draw garments into. */
  begin(width: number, height: number): CanvasRenderingContext2D | null {
    if (this.layer.width !== width || this.layer.height !== height) {
      this.layer.width = width;
      this.layer.height = height;
    }
    const ctx = this.layer.getContext('2d');
    if (!ctx) return null;
    ctx.clearRect(0, 0, width, height);
    return ctx;
  }

  /**
   * Push the garment colour toward the scene light.
   *
   * `source-atop` paints only where the layer already has alpha, so the tint
   * lands on the garment and nowhere else. `multiply` would have been more
   * physically honest but it composites across the whole buffer, turning the
   * transparent background opaque.
   */
  applyLight(light: SceneLight): void {
    if (light.tintStrength <= 0) return;
    const ctx = this.layer.getContext('2d');
    if (!ctx) return;
    ctx.save();
    ctx.globalCompositeOperation = 'source-atop';
    ctx.globalAlpha = light.tintStrength;
    ctx.fillStyle = light.tint;
    ctx.fillRect(0, 0, this.layer.width, this.layer.height);
    ctx.restore();
  }

  /**
   * Clip the layer to the person silhouette.
   *
   * `mask` is MediaPipe's confidence map at its own (small) resolution; the
   * `destination-in` draw scales it up to video space and keeps only the
   * garment pixels that land on the body.
   */
  applyMask(mask: { data: Uint8Array; width: number; height: number }): void {
    const ctx = this.layer.getContext('2d');
    if (!ctx || !mask.width || !mask.height) return;

    if (
      this.maskCanvas.width !== mask.width ||
      this.maskCanvas.height !== mask.height ||
      !this.maskImage
    ) {
      this.maskCanvas.width = mask.width;
      this.maskCanvas.height = mask.height;
      this.maskImage = new ImageData(mask.width, mask.height);
    }
    // Only alpha matters for destination-in; RGB is never sampled.
    const out = this.maskImage.data;
    for (let i = 0, p = 3; i < mask.data.length; i += 1, p += 4) {
      out[p] = mask.data[i];
    }
    const maskCtx = this.maskCanvas.getContext('2d');
    if (!maskCtx) return;
    maskCtx.putImageData(this.maskImage, 0, 0);

    ctx.save();
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(this.maskCanvas, 0, 0, this.layer.width, this.layer.height);
    ctx.restore();
  }

  /** Composite the finished layer onto the visible canvas. */
  commit(ctx: CanvasRenderingContext2D): void {
    ctx.drawImage(this.layer, 0, 0);
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
