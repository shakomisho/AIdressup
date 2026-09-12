/** Left rail: the local clothing catalog, grouped by category. */
'use client';

import { useMemo, useState } from 'react';

import { CATEGORY_LABEL, CATEGORY_ORDER, type Category, type ClothingItem } from '@/lib/types';
import { cn } from '@/lib/utils';
import { useWardrobe } from '@/store/useWardrobe';
import { Pill } from './ui';

function GarmentTile({
  item,
  active,
  onSelect,
}: {
  item: ClothingItem;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        'group relative flex flex-col overflow-hidden rounded-2xl border p-2 text-left transition-all duration-200',
        active
          ? 'border-accent/70 bg-accent/10 shadow-lift'
          : 'border-white/8 bg-white/[0.025] hover:border-white/20 hover:bg-white/[0.06]',
      )}
    >
      <div className="relative mb-2 flex h-24 items-center justify-center rounded-xl bg-gradient-to-b from-white/[0.07] to-transparent">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={item.thumbnail_url ?? item.image_url}
          alt={item.name}
          loading="lazy"
          className="max-h-[88px] max-w-[88%] object-contain drop-shadow-[0_6px_14px_rgba(0,0,0,0.55)] transition-transform duration-300 group-hover:scale-[1.05]"
        />
        {active && (
          <span className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white">
            ✓
          </span>
        )}
      </div>
      <span className="truncate text-[12.5px] font-medium text-white/90">{item.name}</span>
      <span className="truncate text-[11px] text-white/40">{item.brand ?? item.color ?? '—'}</span>
    </button>
  );
}

export function ClothingSidebar() {
  const { items, status, error, worn, toggle, clearOutfit, load, resync } = useWardrobe();
  const [filter, setFilter] = useState<Category | 'all'>('all');
  const [query, setQuery] = useState('');
  const [syncing, setSyncing] = useState(false);

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const visible = items.filter(
      (i) =>
        (filter === 'all' || i.category === filter) &&
        (!needle ||
          i.name.toLowerCase().includes(needle) ||
          (i.brand ?? '').toLowerCase().includes(needle) ||
          i.tags.some((t) => t.toLowerCase().includes(needle))),
    );
    return CATEGORY_ORDER.map((category) => ({
      category,
      label: CATEGORY_LABEL[category],
      items: visible.filter((i) => i.category === category),
    })).filter((g) => g.items.length > 0);
  }, [items, filter, query]);

  const wornCount = Object.keys(worn).length;

  const handleSync = async () => {
    setSyncing(true);
    try {
      await resync();
    } finally {
      setSyncing(false);
    }
  };

  return (
    <aside className="glass flex h-full min-h-0 flex-col overflow-hidden">
      <header className="flex items-center justify-between gap-2 border-b border-white/8 px-4 py-3.5">
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight">Wardrobe</h2>
          <p className="text-[11px] text-white/40">
            {items.length} items · {wornCount} worn
          </p>
        </div>
        <button
          type="button"
          onClick={handleSync}
          disabled={syncing}
          title="Rescan assets/clothes"
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          {syncing ? 'Syncing…' : 'Sync'}
        </button>
      </header>

      <div className="space-y-2.5 px-3 pb-2 pt-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search garments"
          className="field w-full"
        />
        <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
          {(['all', ...CATEGORY_ORDER] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setFilter(c)}
              className={cn(
                'shrink-0 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
                filter === c
                  ? 'bg-white/90 text-ink-900'
                  : 'bg-white/[0.06] text-white/55 hover:text-white/85',
              )}
            >
              {c === 'all' ? 'All' : CATEGORY_LABEL[c]}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {status === 'loading' && (
          <div className="space-y-2 pt-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 animate-pulse-soft rounded-2xl bg-white/[0.05]" />
            ))}
          </div>
        )}

        {status === 'error' && (
          <div className="mt-4 rounded-2xl border border-rose/25 bg-rose/10 p-4 text-[12px] text-rose">
            <p className="font-medium">Catalog unavailable</p>
            <p className="mt-1 text-white/60">{error}</p>
            <p className="mt-2 text-white/45">
              Start the API: <code className="font-mono">uvicorn app.main:app --port 8000</code>
            </p>
            <button type="button" onClick={() => void load()} className="btn-ghost mt-3 text-xs">
              Retry
            </button>
          </div>
        )}

        {status === 'ready' && grouped.length === 0 && (
          <p className="px-1 pt-6 text-center text-[12px] text-white/40">
            No garments match. Drop PNGs into <code>assets/clothes/</code> and hit Sync.
          </p>
        )}

        <div className="space-y-5 pt-1">
          {grouped.map((group) => (
            <div key={group.category}>
              <div className="mb-2 flex items-center justify-between px-1">
                <h3 className="panel-title">{group.label}</h3>
                <span className="text-[11px] text-white/30">{group.items.length}</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {group.items.map((item) => (
                  <GarmentTile
                    key={item.id}
                    item={item}
                    active={worn[item.category] === item.id}
                    onSelect={() => toggle(item)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <footer className="flex items-center justify-between gap-2 border-t border-white/8 px-3 py-2.5">
        <Pill tone={wornCount ? 'accent' : 'neutral'}>
          {wornCount ? `${wornCount} layer${wornCount > 1 ? 's' : ''}` : 'Nothing on'}
        </Pill>
        <button
          type="button"
          onClick={clearOutfit}
          disabled={!wornCount}
          className="btn-ghost px-3 py-1.5 text-xs"
        >
          Take off all
        </button>
      </footer>
    </aside>
  );
}
