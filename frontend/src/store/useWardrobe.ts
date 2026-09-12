/**
 * Catalog + current outfit.
 *
 * One garment may be worn per category, so layering (jeans + tee + jacket)
 * works; clicking the active item takes it off. Sprites are preloaded into
 * `HTMLImageElement`s here so the render loop never waits on a decode.
 */
'use client';

import { useMemo } from 'react';
import { create } from 'zustand';

import { api } from '@/lib/api';
import type { Category, ClothingItem } from '@/lib/types';

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

interface WardrobeState {
  items: ClothingItem[];
  status: LoadState;
  error: string | null;
  /** category -> selected item id */
  worn: Partial<Record<Category, number>>;
  /** item id -> decoded sprite */
  sprites: Map<number, HTMLImageElement>;

  load(): Promise<void>;
  resync(): Promise<void>;
  toggle(item: ClothingItem): void;
  clearOutfit(): void;
  wornItems(): ClothingItem[];
}

function preload(item: ClothingItem, sprites: Map<number, HTMLImageElement>): void {
  if (sprites.has(item.id)) return;
  const img = new Image();
  // Same-origin via the Next rewrite, but be explicit so the canvas is never
  // tainted if someone points NEXT_PUBLIC_API_URL at another host.
  img.crossOrigin = 'anonymous';
  img.decoding = 'async';
  img.src = item.image_url;
  sprites.set(item.id, img);
}

export const useWardrobe = create<WardrobeState>()((set, get) => ({
  items: [],
  status: 'idle',
  error: null,
  worn: {},
  sprites: new Map(),

  load: async () => {
    set({ status: 'loading', error: null });
    try {
      const items = await api.clothing();
      const sprites = get().sprites;
      items.forEach((item) => preload(item, sprites));
      set({ items, status: 'ready', sprites });

      // Auto-wear the first shirt: Phase 1 ships shirt support first.
      if (!Object.keys(get().worn).length) {
        const shirt = items.find((i) => i.category === 'shirts');
        if (shirt) set({ worn: { shirts: shirt.id } });
      }
    } catch (err) {
      set({ status: 'error', error: err instanceof Error ? err.message : 'catalog unavailable' });
    }
  },

  resync: async () => {
    await api.syncCatalog();
    await get().load();
  },

  toggle: (item) => {
    const worn = { ...get().worn };
    if (worn[item.category] === item.id) delete worn[item.category];
    else worn[item.category] = item.id;
    set({ worn });
  },

  clearOutfit: () => set({ worn: {} }),

  wornItems: () => selectWorn(get().items, get().worn),
}));

function selectWorn(
  items: ClothingItem[],
  worn: Partial<Record<Category, number>>,
): ClothingItem[] {
  const ids = new Set(Object.values(worn));
  return items
    .filter((i) => ids.has(i.id))
    .sort((a, b) => a.overlay.z_index - b.overlay.z_index);
}

/**
 * Memoized view of the current outfit for components.
 *
 * `wornItems()` builds a new array on every call, so using it directly as a
 * zustand selector would return a fresh reference each render and loop forever.
 * Components subscribe to the two primitives and derive from them instead.
 */
export function useWornItems(): ClothingItem[] {
  const items = useWardrobe((s) => s.items);
  const worn = useWardrobe((s) => s.worn);
  return useMemo(() => selectWorn(items, worn), [items, worn]);
}
