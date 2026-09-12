/**
 * Three-column studio layout:
 *   left   clothing catalog
 *   center large camera preview
 *   right  settings + diagnostics
 * Columns collapse into a single scrollable stack below `xl`.
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { CameraStage } from '@/components/CameraStage';
import { ClothingSidebar } from '@/components/ClothingSidebar';
import { SettingsPanel } from '@/components/SettingsPanel';
import { TopBar } from '@/components/TopBar';
import { api } from '@/lib/api';
import { useWardrobe } from '@/store/useWardrobe';

interface Stats {
  fps: number;
  avgFps: number;
  frames: number;
  inferenceMs: number;
}

export default function StudioPage() {
  const load = useWardrobe((w) => w.load);
  const [stats, setStats] = useState<Stats>({ fps: 0, avgFps: 0, frames: 0, inferenceMs: 0 });
  const [sessionId, setSessionId] = useState<string | null>(null);
  const statsRef = useRef(stats);

  statsRef.current = stats;

  useEffect(() => {
    void load();
  }, [load]);

  // Open a session row so FPS telemetry has somewhere to land.
  useEffect(() => {
    let publicId: string | null = null;
    api
      .createSession({ user_agent: navigator.userAgent })
      .then((s) => {
        publicId = s.public_id;
        setSessionId(s.public_id);
      })
      .catch(() => undefined);

    const flush = (ended: boolean) => {
      if (!publicId) return;
      const { avgFps, frames } = statsRef.current;
      if (!frames) return;
      void api
        .updateSession(publicId, { avg_fps: avgFps, frames_processed: frames, ended })
        .catch(() => undefined);
    };

    const timer = setInterval(() => flush(false), 20_000);
    const onUnload = () => flush(true);
    window.addEventListener('pagehide', onUnload);

    return () => {
      clearInterval(timer);
      window.removeEventListener('pagehide', onUnload);
      flush(true);
    };
  }, []);

  const handleStats = useCallback((next: Stats) => setStats(next), []);

  return (
    <main className="mx-auto flex h-screen max-w-[1800px] flex-col gap-3 p-3 md:p-4">
      <TopBar />
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-y-auto xl:grid-cols-[300px_minmax(0,1fr)_320px] xl:overflow-hidden">
        <div className="order-2 min-h-[420px] xl:order-1 xl:min-h-0">
          <ClothingSidebar />
        </div>
        <div className="order-1 min-h-[52vh] xl:order-2 xl:min-h-0">
          <CameraStage sessionId={sessionId} onStats={handleStats} />
        </div>
        <div className="order-3 min-h-0">
          <SettingsPanel stats={stats} />
        </div>
      </div>
    </main>
  );
}
