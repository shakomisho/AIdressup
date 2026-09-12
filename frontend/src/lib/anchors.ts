/**
 * Landmark -> garment transform. Mirror of
 * `backend/app/tryon/overlay_engine.py::solve_placements`; keep both in sync.
 *
 * Orientation is derived from the **body axis** (hips -> shoulders), never from
 * the left/right landmark ordering, so a mirrored selfie feed renders the same.
 * Scale is driven by a reference landmark distance measured in pixels, so the
 * garment grows and shrinks with the person's distance from the camera.
 */
import type { AnchorType, Landmark, OverlayConfig } from './types';

/** BlazePose 33-point indices used by the overlay. */
export const LM = {
  NOSE: 0,
  LEFT_EYE_OUTER: 3,
  RIGHT_EYE_OUTER: 6,
  LEFT_EAR: 7,
  RIGHT_EAR: 8,
  LEFT_SHOULDER: 11,
  RIGHT_SHOULDER: 12,
  LEFT_HIP: 23,
  RIGHT_HIP: 24,
  LEFT_KNEE: 25,
  RIGHT_KNEE: 26,
  LEFT_ANKLE: 27,
  RIGHT_ANKLE: 28,
  LEFT_FOOT: 31,
  RIGHT_FOOT: 32,
} as const;

/** Landmarks that must be visible before a given anchor can be solved. */
const REQUIRED: Record<AnchorType, number[]> = {
  torso: [LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER, LM.LEFT_HIP, LM.RIGHT_HIP],
  hips: [LM.LEFT_HIP, LM.RIGHT_HIP, LM.LEFT_KNEE, LM.RIGHT_KNEE],
  head: [LM.LEFT_EAR, LM.RIGHT_EAR, LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER],
  feet: [LM.LEFT_ANKLE, LM.RIGHT_ANKLE, LM.LEFT_FOOT, LM.RIGHT_FOOT],
  eyes: [LM.LEFT_EYE_OUTER, LM.RIGHT_EYE_OUTER, LM.LEFT_SHOULDER, LM.RIGHT_SHOULDER],
};

export interface Point {
  x: number;
  y: number;
}

export interface Placement {
  /** Anchor position in pixels. */
  cx: number;
  cy: number;
  /** Garment width in pixels (height follows the PNG aspect ratio). */
  width: number;
  /** Clockwise rotation in radians. */
  angle: number;
  /** Sprite must be flipped horizontally (left foot vs right foot). */
  mirror: boolean;
}

const px = (l: Landmark[], i: number, w: number, h: number): Point => ({
  x: l[i].x * w,
  y: l[i].y * h,
});

const mid = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

const dist = (a: Point, b: Point): number => Math.hypot(a.x - b.x, a.y - b.y);

const norm = (v: Point): Point => {
  const len = Math.hypot(v.x, v.y) || 1;
  return { x: v.x / len, y: v.y / len };
};

/** Clockwise screen-space roll of a garment whose PNG points up. */
const axisAngle = (up: Point): number => Math.atan2(up.x, -up.y);

export function isVisible(
  landmarks: Landmark[],
  anchor: AnchorType,
  threshold = 0.5,
): boolean {
  return REQUIRED[anchor].every((i) => {
    const l = landmarks[i];
    if (!l) return false;
    return l.visibility === undefined || l.visibility >= threshold;
  });
}

function place(
  anchor: Point,
  up: Point,
  span: number,
  cfg: Pick<OverlayConfig, 'scale_multiplier' | 'offset_x' | 'offset_y' | 'rotation_offset'>,
  mirror = false,
): Placement {
  // Body frame: +x = screen-right of the body axis, +y = down the body axis.
  const right = { x: -up.y, y: up.x };
  return {
    cx: anchor.x + span * (cfg.offset_x * right.x - cfg.offset_y * up.x),
    cy: anchor.y + span * (cfg.offset_x * right.y - cfg.offset_y * up.y),
    width: span * cfg.scale_multiplier,
    angle: axisAngle(up) + (cfg.rotation_offset * Math.PI) / 180,
    mirror,
  };
}

/**
 * Solve one placement per garment instance. Shoes return two (one per foot);
 * everything else returns one. Returns `[]` when the required landmarks are
 * not confidently visible.
 */
export function solvePlacements(
  landmarks: Landmark[],
  frameWidth: number,
  frameHeight: number,
  cfg: OverlayConfig,
  visibilityThreshold = 0.5,
): Placement[] {
  if (!landmarks || landmarks.length < 33) return [];
  if (!isVisible(landmarks, cfg.anchor_type, visibilityThreshold)) return [];
  const p = (i: number) => px(landmarks, i, frameWidth, frameHeight);

  switch (cfg.anchor_type) {
    case 'torso': {
      const shoulders = mid(p(LM.LEFT_SHOULDER), p(LM.RIGHT_SHOULDER));
      const hips = mid(p(LM.LEFT_HIP), p(LM.RIGHT_HIP));
      const span = Math.max(dist(p(LM.LEFT_SHOULDER), p(LM.RIGHT_SHOULDER)), 1);
      const up = norm({ x: shoulders.x - hips.x, y: shoulders.y - hips.y });
      return [place(shoulders, up, span, cfg)];
    }
    case 'hips': {
      const hips = mid(p(LM.LEFT_HIP), p(LM.RIGHT_HIP));
      const knees = mid(p(LM.LEFT_KNEE), p(LM.RIGHT_KNEE));
      const span = Math.max(dist(p(LM.LEFT_HIP), p(LM.RIGHT_HIP)), 1);
      const up = norm({ x: hips.x - knees.x, y: hips.y - knees.y });
      return [place(hips, up, span, cfg)];
    }
    case 'head': {
      const ears = mid(p(LM.LEFT_EAR), p(LM.RIGHT_EAR));
      const shoulders = mid(p(LM.LEFT_SHOULDER), p(LM.RIGHT_SHOULDER));
      const span = Math.max(dist(p(LM.LEFT_EAR), p(LM.RIGHT_EAR)), 1);
      const up = norm({ x: ears.x - shoulders.x, y: ears.y - shoulders.y });
      return [place(ears, up, span, cfg)];
    }
    case 'eyes': {
      const a = p(LM.LEFT_EYE_OUTER);
      const b = p(LM.RIGHT_EYE_OUTER);
      const eyes = mid(a, b);
      const shoulders = mid(p(LM.LEFT_SHOULDER), p(LM.RIGHT_SHOULDER));
      const span = Math.max(dist(a, b), 1);
      // Roll comes from the eye line, which tracks a tilted head far better
      // than ears -> shoulders does. The eye line is an *undirected* axis, so
      // its perpendicular has two candidates; pick the one pointing away from
      // the shoulders. That choice is mirror-invariant, where relying on the
      // left/right landmark order would flip the frames upside down in a
      // selfie feed.
      const axis = norm({ x: a.x - b.x, y: a.y - b.y });
      let up = { x: axis.y, y: -axis.x };
      const bodyUp = { x: eyes.x - shoulders.x, y: eyes.y - shoulders.y };
      if (up.x * bodyUp.x + up.y * bodyUp.y < 0) up = { x: -up.x, y: -up.y };
      return [place(eyes, up, span, cfg)];
    }
    case 'feet': {
      const feet: [number, number][] = [
        [LM.LEFT_ANKLE, LM.LEFT_FOOT],
        [LM.RIGHT_ANKLE, LM.RIGHT_FOOT],
      ];
      return feet.map(([ankleIdx, toeIdx]) => {
        const ankle = p(ankleIdx);
        const toe = p(toeIdx);
        const span = Math.max(dist(ankle, toe), 1);
        const mirror = toe.x < ankle.x;
        let forward = norm({ x: toe.x - ankle.x, y: toe.y - ankle.y });
        // The PNG points toe-right; mirror instead of rotating past vertical.
        if (mirror) forward = { x: -forward.x, y: forward.y };
        const up = { x: forward.y, y: -forward.x };
        const flip = mirror ? -1 : 1;
        return place(
          ankle,
          up,
          span,
          {
            ...cfg,
            offset_x: cfg.offset_x * flip,
            rotation_offset: cfg.rotation_offset * flip,
          },
          mirror,
        );
      });
    }
    default:
      return [];
  }
}

/** Merge per-garment calibration with the live settings-panel adjustments. */
export function effectiveOverlay(
  base: OverlayConfig,
  adjust: { scaleAdjust: number; offsetX: number; offsetY: number; clothingOpacity: number },
): OverlayConfig {
  return {
    ...base,
    scale_multiplier: base.scale_multiplier * adjust.scaleAdjust,
    offset_x: base.offset_x + adjust.offsetX,
    offset_y: base.offset_y + adjust.offsetY,
    opacity: base.opacity * adjust.clothingOpacity,
  };
}
