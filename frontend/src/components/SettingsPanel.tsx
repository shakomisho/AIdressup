/** Right rail: tracking, fit tuning, engine selection and diagnostics. */
'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import type { Delegate, ModelVariant } from '@/lib/pose';
import type { EngineInfo, HealthInfo } from '@/lib/types';
import { formatBytes } from '@/lib/utils';
import { useSettings } from '@/store/useSettings';
import { useWornItems } from '@/store/useWardrobe';
import { Pill, SectionCard, Segmented, Slider, Toggle } from './ui';

interface Props {
  stats: { fps: number; avgFps: number; frames: number; inferenceMs: number };
}

export function SettingsPanel({ stats }: Props) {
  const s = useSettings();
  const wornItems = useWornItems();
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [cache, setCache] = useState<{ entries: number; total_hits: number; bytes_on_disk: number } | null>(
    null,
  );

  useEffect(() => {
    void s.hydrateFromServer();
    api.health().then(setHealth).catch(() => undefined);
    api.engines().then(setEngines).catch(() => undefined);
    api.cacheStats().then(setCache).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshCache = () => api.cacheStats().then(setCache).catch(() => undefined);

  return (
    <aside className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pb-1">
      <SectionCard
        title="Tracking"
        action={
          <Pill tone={stats.fps >= 30 ? 'good' : stats.fps > 0 ? 'warn' : 'neutral'}>
            {stats.fps.toFixed(0)} fps
          </Pill>
        }
      >
        <Toggle
          label="Skeleton"
          hint="Connect landmarks with lines"
          checked={s.showSkeleton}
          onChange={(v) => s.set('showSkeleton', v)}
        />
        <Toggle
          label="Landmarks"
          hint="33 BlazePose joints"
          checked={s.showLandmarks}
          onChange={(v) => s.set('showLandmarks', v)}
        />
        <Toggle label="Clothing" checked={s.showClothing} onChange={(v) => s.set('showClothing', v)} />
        <Toggle
          label="Mirror"
          hint="Selfie view"
          checked={s.mirror}
          onChange={(v) => s.set('mirror', v)}
        />
        <Toggle label="FPS badge" checked={s.showFps} onChange={(v) => s.set('showFps', v)} />
      </SectionCard>

      <SectionCard title="Pose model">
        <Segmented<ModelVariant>
          value={s.modelVariant}
          onChange={(v) => s.set('modelVariant', v)}
          options={[
            { value: 'lite', label: 'Lite', hint: 'Fastest — best for 30+ FPS' },
            { value: 'full', label: 'Full', hint: 'Balanced accuracy' },
            { value: 'heavy', label: 'Heavy', hint: 'Most accurate, slowest' },
          ]}
        />
        <Segmented<Delegate>
          value={s.delegate}
          onChange={(v) => s.set('delegate', v)}
          options={[
            { value: 'GPU', label: 'GPU', hint: 'WebGL delegate' },
            { value: 'CPU', label: 'CPU', hint: 'Fallback' },
          ]}
        />
        <Slider
          label="Smoothing"
          value={s.smoothing}
          min={0}
          max={1}
          onChange={(v) => s.set('smoothing', v)}
          format={(v) => (v === 0 ? 'off' : v.toFixed(2))}
        />
        <Slider
          label="Visibility cutoff"
          value={s.visibilityThreshold}
          min={0.1}
          max={0.9}
          onChange={(v) => s.set('visibilityThreshold', v)}
        />
      </SectionCard>

      <SectionCard
        title="Fit"
        action={
          <button
            type="button"
            className="text-[11px] text-white/40 transition hover:text-white/80"
            onClick={() => {
              s.set('scaleAdjust', 1);
              s.set('offsetX', 0);
              s.set('offsetY', 0);
              s.set('clothingOpacity', 1);
            }}
          >
            Reset
          </button>
        }
      >
        <Slider
          label="Size"
          value={s.scaleAdjust}
          min={0.6}
          max={1.6}
          onChange={(v) => s.set('scaleAdjust', v)}
          format={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <Slider
          label="Horizontal"
          value={s.offsetX}
          min={-0.5}
          max={0.5}
          onChange={(v) => s.set('offsetX', v)}
        />
        <Slider
          label="Vertical"
          value={s.offsetY}
          min={-0.5}
          max={0.5}
          onChange={(v) => s.set('offsetY', v)}
        />
        <Slider
          label="Opacity"
          value={s.clothingOpacity}
          min={0.2}
          max={1}
          onChange={(v) => s.set('clothingOpacity', v)}
          format={(v) => `${(v * 100).toFixed(0)}%`}
        />
        <p className="px-3 pb-1 pt-1 text-[11px] leading-relaxed text-white/35">
          Adjustments stack on each garment&apos;s own calibration from
          <code className="mx-1 font-mono">catalog.json</code>.
        </p>
      </SectionCard>

      <SectionCard title="Try-on engine">
        <div className="space-y-1.5 px-1 py-1">
          {engines.map((e) => (
            <button
              key={e.name}
              type="button"
              disabled={!e.available}
              onClick={() => s.set('engine', e.name)}
              className={[
                'w-full rounded-2xl border px-3 py-2.5 text-left transition-all',
                s.engine === e.name
                  ? 'border-accent/60 bg-accent/10'
                  : 'border-white/8 bg-white/[0.025] hover:bg-white/[0.06]',
                !e.available && 'opacity-45',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-medium">{e.title}</span>
                <div className="flex items-center gap-1.5">
                  {e.execution === 'queued' && <Pill>queued</Pill>}
                  <Pill tone={e.available ? 'good' : 'neutral'}>
                    {e.available ? 'ready' : `phase ${e.phase}`}
                  </Pill>
                </div>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-white/40">{e.description}</p>
            </button>
          ))}
          {!engines.length && <p className="px-2 text-[12px] text-white/35">Backend offline.</p>}
        </div>
      </SectionCard>

      <SectionCard
        title="Cache"
        action={
          <button
            type="button"
            onClick={async () => {
              await api.clearCache().catch(() => undefined);
              void refreshCache();
            }}
            className="text-[11px] text-white/40 transition hover:text-rose"
          >
            Clear
          </button>
        }
      >
        <dl className="grid grid-cols-3 gap-2 px-2 py-1 text-center">
          {[
            ['Entries', cache?.entries ?? 0],
            ['Hits', cache?.total_hits ?? 0],
            ['On disk', formatBytes(cache?.bytes_on_disk ?? 0)],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl bg-white/[0.04] py-2">
              <dt className="text-[10px] uppercase tracking-wider text-white/35">{label}</dt>
              <dd className="mt-0.5 font-mono text-[13px] text-white/85">{value}</dd>
            </div>
          ))}
        </dl>
      </SectionCard>

      <SectionCard title="Diagnostics">
        <dl className="space-y-1.5 px-3 py-1 font-mono text-[11.5px]">
          {[
            ['avg fps', stats.avgFps.toFixed(1)],
            ['frames', String(stats.frames)],
            ['pose', `${stats.inferenceMs.toFixed(1)} ms`],
            ['layers', String(wornItems.length)],
            ['api', health ? `v${health.version} · ${health.database}` : 'offline'],
            ['catalog', health ? `${health.catalog_items} items` : '—'],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt className="text-white/35">{k}</dt>
              <dd className="truncate text-white/75">{v}</dd>
            </div>
          ))}
        </dl>
        <button type="button" onClick={() => s.reset()} className="btn-ghost mx-3 mb-1 mt-2 text-xs">
          Reset all settings
        </button>
      </SectionCard>
    </aside>
  );
}
