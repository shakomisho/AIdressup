/**
 * Scene light estimation.
 *
 * A garment sprite is lit however it was photographed; the person is lit by
 * whatever room they are standing in. That mismatch is one of the strongest
 * "this is a sticker" cues, and it is cheap to soften: measure the mean colour
 * of the frame, then push the sprite's brightness and hue toward it.
 *
 * Mirrored by `sample_scene_light` in `backend/app/tryon/overlay_engine.py`;
 * keep the two in sync.
 */

/** How strongly the scene colour is allowed to tint the garment (0..1). */
const TINT_STRENGTH = 0.18;

/** Brightness is clamped hard — a dim room should shade a shirt, not erase it. */
const MIN_BRIGHTNESS = 0.7;
const MAX_BRIGHTNESS = 1.15;

/** Sampling grid. 32x32 is ~1000 pixels: plenty for a mean, trivial to read back. */
const GRID = 32;

export interface SceneLight {
  /** Multiplier for the garment's luminance. */
  brightness: number;
  /** Mean scene colour, as a CSS rgb() string. */
  tint: string;
  /** How far to blend `tint` over the garment (0..1). */
  tintStrength: number;
}

export const NEUTRAL_LIGHT: SceneLight = {
  brightness: 1,
  tint: 'rgb(255,255,255)',
  tintStrength: 0,
};

let scratch: HTMLCanvasElement | null = null;

function getScratch(): CanvasRenderingContext2D | null {
  if (!scratch) {
    scratch = document.createElement('canvas');
    scratch.width = GRID;
    scratch.height = GRID;
  }
  // willReadFrequently keeps the surface on the CPU; without it every
  // getImageData forces a GPU readback and the loop stutters.
  return scratch.getContext('2d', { willReadFrequently: true });
}

/**
 * Measure the mean colour of a frame.
 *
 * Call this at a few Hz, not every frame — room lighting does not change at
 * 30 FPS, and `getImageData` is the most expensive thing in the render loop.
 */
export function sampleSceneLight(
  source: CanvasImageSource & { width?: number; height?: number },
): SceneLight {
  const ctx = getScratch();
  if (!ctx) return NEUTRAL_LIGHT;

  try {
    ctx.drawImage(source, 0, 0, GRID, GRID);
  } catch {
    // Tainted canvas or a video with no decoded frame yet.
    return NEUTRAL_LIGHT;
  }

  let r = 0;
  let g = 0;
  let b = 0;
  const { data } = ctx.getImageData(0, 0, GRID, GRID);
  const pixels = data.length / 4;
  for (let i = 0; i < data.length; i += 4) {
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
  }
  r /= pixels;
  g /= pixels;
  b /= pixels;

  // Rec. 709 luma, normalised so a mid-grey scene (128) leaves the garment alone.
  const luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const brightness = clamp(0.55 + luma * 0.9, MIN_BRIGHTNESS, MAX_BRIGHTNESS);

  // Normalise the mean to full value so the tint carries the scene's *hue*
  // without darkening the sprite a second time — brightness already did that.
  const peak = Math.max(r, g, b, 1);
  const scale = 255 / peak;

  return {
    brightness,
    tint: `rgb(${Math.round(r * scale)},${Math.round(g * scale)},${Math.round(b * scale)})`,
    tintStrength: TINT_STRENGTH,
  };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}
