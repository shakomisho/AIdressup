export type Category = 'shirts' | 'pants' | 'jackets' | 'hats' | 'shoes' | 'glasses';
export type AnchorType = 'torso' | 'hips' | 'head' | 'feet' | 'eyes';

export interface OverlayConfig {
  anchor_type: AnchorType;
  /** Garment PNG width expressed in multiples of the reference landmark span. */
  scale_multiplier: number;
  /** Offsets in body-frame units of the reference span (+x right, +y down). */
  offset_x: number;
  offset_y: number;
  rotation_offset: number;
  /** Where the landmark anchor sits inside the PNG, 0..1. */
  pivot_x: number;
  pivot_y: number;
  opacity: number;
  z_index: number;
}

export interface ClothingItem {
  id: number;
  slug: string;
  name: string;
  category: Category;
  file_path: string;
  image_url: string;
  thumbnail_url: string | null;
  natural_width: number | null;
  natural_height: number | null;
  brand: string | null;
  color: string | null;
  size: string | null;
  tags: string[];
  description: string | null;
  is_active: boolean;
  overlay: OverlayConfig;
  created_at: string;
}

export interface CategoryCount {
  category: Category;
  label: string;
  count: number;
}

/**
 * `inline` — POST /api/tryon returns the finished image (200).
 * `queued` — POST returns 202 with status `pending`; poll the result endpoint.
 * See docs/adr/0001-phase-2-inference-execution.md.
 */
export type ExecutionMode = 'inline' | 'queued';

export interface EngineInfo {
  name: string;
  title: string;
  description: string;
  available: boolean;
  phase: number;
  requires: string[];
  execution: ExecutionMode;
}

export interface HealthInfo {
  status: string;
  version: string;
  environment: string;
  database: string;
  clothes_dir: string;
  catalog_items: number;
  default_engine: string;
  engines: EngineInfo[];
}

export interface SessionInfo {
  id: number;
  public_id: string;
  started_at: string;
  ended_at: string | null;
  avg_fps: number | null;
  frames_processed: number;
}

export type ResultStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';

export const TERMINAL_STATUSES: ResultStatus[] = ['completed', 'failed', 'cancelled'];

export function isTerminal(status: ResultStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export interface TryOnResult {
  id: number;
  public_id: string;
  clothing_item_id: number;
  engine: string;
  status: ResultStatus;
  input_hash: string;
  output_url: string | null;
  latency_ms: number | null;
  cached: boolean;
  error: string | null;
  /** 0..1 while a queued engine runs. */
  progress: number;
  cancelled: boolean;
  created_at: string;
}

/** A MediaPipe normalised landmark. */
export interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility?: number;
}

export const CATEGORY_ORDER: Category[] = [
  'shirts',
  'jackets',
  'pants',
  'hats',
  'glasses',
  'shoes',
];

export const CATEGORY_LABEL: Record<Category, string> = {
  shirts: 'Shirts',
  jackets: 'Jackets',
  pants: 'Pants',
  hats: 'Hats',
  glasses: 'Glasses',
  shoes: 'Shoes',
};
