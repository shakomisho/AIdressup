'use client';

import { useWornItems } from '@/store/useWardrobe';
import { Pill } from './ui';

export function TopBar({ phase = 1 }: { phase?: number }) {
  const worn = useWornItems();

  return (
    <header className="flex items-center justify-between gap-4 px-1 py-1">
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-2xl bg-gradient-to-br from-accent to-[#5e5ce6] text-[15px] shadow-lift">
          👕
        </div>
        <div>
          <h1 className="text-[15px] font-semibold leading-tight tracking-tight">
            AI Virtual Try-On
          </h1>
          <p className="text-[11px] text-white/40">
            MediaPipe Pose · local catalog · phase {phase}
          </p>
        </div>
      </div>

      <div className="hidden items-center gap-2 md:flex">
        {worn.length ? (
          worn.map((item) => (
            <Pill key={item.id} tone="accent">
              {item.name}
            </Pill>
          ))
        ) : (
          <Pill>Select a garment</Pill>
        )}
      </div>
    </header>
  );
}
