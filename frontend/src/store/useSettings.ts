/**
 * Settings panel state.
 *
 * Persisted to localStorage for instant restore, and mirrored to the backend
 * (`app_settings` table) on a debounce so the preferences survive a new browser.
 */
'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { api } from '@/lib/api';
import type { Delegate, ModelVariant } from '@/lib/pose';
import { debounce } from '@/lib/utils';

export interface SettingsState {
  // --- tracking overlay ---
  showSkeleton: boolean;
  showLandmarks: boolean;
  showClothing: boolean;
  showFps: boolean;
  mirror: boolean;
  // --- pose engine ---
  modelVariant: ModelVariant;
  delegate: Delegate;
  smoothing: number;
  visibilityThreshold: number;
  // --- garment tuning (applied on top of each item's calibration) ---
  clothingOpacity: number;
  scaleAdjust: number;
  offsetX: number;
  offsetY: number;
  // --- phase 2 ---
  engine: string;

  set<K extends keyof SettingsState>(key: K, value: SettingsState[K]): void;
  reset(): void;
  hydrateFromServer(): Promise<void>;
}

export const DEFAULTS = {
  showSkeleton: true,
  showLandmarks: true,
  showClothing: true,
  showFps: true,
  mirror: true,
  modelVariant: 'lite' as ModelVariant,
  delegate: 'GPU' as Delegate,
  smoothing: 0.6,
  visibilityThreshold: 0.5,
  clothingOpacity: 1,
  scaleAdjust: 1,
  offsetX: 0,
  offsetY: 0,
  engine: 'overlay',
};

/** Keys the backend also knows about (see backend/app/routers/settings.py). */
const SERVER_KEYS = [
  'showSkeleton',
  'showLandmarks',
  'showClothing',
  'showFps',
  'mirror',
  'modelVariant',
  'delegate',
  'smoothing',
  'clothingOpacity',
  'scaleAdjust',
  'offsetX',
  'offsetY',
  'engine',
] as const;

const pushToServer = debounce((state: Record<string, unknown>) => {
  const payload: Record<string, unknown> = {};
  for (const key of SERVER_KEYS) payload[key] = state[key];
  api.putSettings(payload).catch(() => {
    /* offline backend must not break the UI */
  });
}, 900);

export const useSettings = create<SettingsState>()(
  persist(
    (set, get) => ({
      ...DEFAULTS,

      set: (key, value) => {
        set({ [key]: value } as Pick<SettingsState, typeof key>);
        pushToServer(get() as unknown as Record<string, unknown>);
      },

      reset: () => {
        set({ ...DEFAULTS });
        pushToServer(DEFAULTS as unknown as Record<string, unknown>);
      },

      hydrateFromServer: async () => {
        try {
          const { values } = await api.getSettings();
          const patch: Record<string, unknown> = {};
          for (const key of SERVER_KEYS) {
            if (values[key] !== undefined) patch[key] = values[key];
          }
          set(patch as Partial<SettingsState>);
        } catch {
          /* keep local values */
        }
      },
    }),
    {
      name: 'tryon-settings',
      partialize: (state) =>
        Object.fromEntries(
          Object.entries(state).filter(([, v]) => typeof v !== 'function'),
        ) as SettingsState,
    },
  ),
);
