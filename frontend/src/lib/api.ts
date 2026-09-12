/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Requests go to same-origin `/api/...` and are proxied by next.config.mjs, so
 * garment images are same-origin too and never taint the overlay canvas.
 */
import type {
  Category,
  CategoryCount,
  ClothingItem,
  EngineInfo,
  HealthInfo,
  SessionInfo,
  TryOnResult,
} from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthInfo>('/api/health'),

  clothing: (params: { category?: Category; search?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.category) qs.set('category', params.category);
    if (params.search) qs.set('search', params.search);
    const suffix = qs.toString() ? `?${qs}` : '';
    return request<ClothingItem[]>(`/api/clothing${suffix}`);
  },

  categories: () => request<CategoryCount[]>('/api/clothing/categories'),

  syncCatalog: () =>
    request<{ added: string[]; updated: string[]; deactivated: string[]; total_active: number }>(
      '/api/clothing/sync',
      { method: 'POST' },
    ),

  updateClothing: (id: number, patch: Record<string, unknown>) =>
    request<ClothingItem>(`/api/clothing/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  engines: () => request<EngineInfo[]>('/api/tryon/engines'),

  createSession: (payload: {
    user_agent?: string;
    camera_label?: string;
    frame_width?: number;
    frame_height?: number;
  }) => request<SessionInfo>('/api/sessions', { method: 'POST', body: JSON.stringify(payload) }),

  updateSession: (
    publicId: string,
    patch: { avg_fps?: number; frames_processed?: number; ended?: boolean },
  ) =>
    request<SessionInfo>(`/api/sessions/${publicId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  /** Phase 2 path: hand a frame + garment to a server-side engine. */
  tryOn: (payload: {
    clothing_id: number;
    person_image: string;
    engine?: string;
    session_public_id?: string;
    pose_landmarks?: unknown;
    params?: Record<string, unknown>;
    use_cache?: boolean;
  }) => request<TryOnResult>('/api/tryon', { method: 'POST', body: JSON.stringify(payload) }),

  /** Poll target for queued engines. */
  tryOnResult: (publicId: string) => request<TryOnResult>(`/api/tryon/${publicId}`),

  cancelTryOn: (publicId: string) =>
    request<TryOnResult>(`/api/tryon/${publicId}/cancel`, { method: 'POST' }),

  queueStats: () => request<{ depth: number }>('/api/tryon/queue'),

  results: (clothingId?: number) =>
    request<TryOnResult[]>(
      `/api/tryon/results${clothingId ? `?clothing_id=${clothingId}` : ''}`,
    ),

  cacheStats: () =>
    request<{ entries: number; total_hits: number; results: number; bytes_on_disk: number }>(
      '/api/tryon/cache',
    ),

  clearCache: () => request<{ removed: number }>('/api/tryon/cache', { method: 'DELETE' }),

  getSettings: () => request<{ values: Record<string, unknown> }>('/api/settings'),

  putSettings: (values: Record<string, unknown>) =>
    request<{ values: Record<string, unknown> }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify({ values }),
    }),
};
