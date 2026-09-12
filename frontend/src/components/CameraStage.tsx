/** Center stage: live webcam, pose overlay canvas, HUD and capture controls. */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { usePoseOverlay } from '@/hooks/usePoseOverlay';
import { useWebcam } from '@/hooks/useWebcam';
import { api } from '@/lib/api';
import { captureFrame } from '@/lib/draw';
import { isTerminal, type TryOnResult } from '@/lib/types';
import { cn, downloadDataUrl } from '@/lib/utils';
import { useSettings } from '@/store/useSettings';
import { useWardrobe } from '@/store/useWardrobe';
import { Pill } from './ui';

interface Props {
  sessionId: string | null;
  onStats: (stats: { fps: number; avgFps: number; frames: number; inferenceMs: number }) => void;
}

/** Poll cadence for queued engines. Diffusion runs for seconds, so this is
 *  responsive enough without hammering the API. */
const POLL_MS = 400;

export function CameraStage({ sessionId, onStats }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<TryOnResult | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  /** Lets an unmount (or a newer request) abandon an in-flight poll loop. */
  const pollRef = useRef<{ abandoned: boolean } | null>(null);

  const mirror = useSettings((s) => s.mirror);
  const showFps = useSettings((s) => s.showFps);
  const engine = useSettings((s) => s.engine);

  const camera = useWebcam(videoRef);
  const tracker = usePoseOverlay({
    videoRef,
    canvasRef,
    enabled: camera.status === 'live' && !paused,
  });

  useEffect(() => {
    onStats({
      fps: tracker.fps,
      avgFps: tracker.avgFps,
      frames: tracker.frames,
      inferenceMs: tracker.inferenceMs,
    });
  }, [tracker.fps, tracker.avgFps, tracker.frames, tracker.inferenceMs, onStats]);

  const grabFrame = useCallback(
    (includeOverlay: boolean) => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas) return null;
      return captureFrame(video, canvas, mirror, includeOverlay);
    },
    [mirror],
  );

  const handleSnapshot = useCallback(() => {
    const frame = grabFrame(true);
    if (!frame) return;
    const url = frame.toDataURL('image/png');
    setSnapshot(url);
    setAiResult(null);
    setAiError(null);
  }, [grabFrame]);

  /**
   * Phase 2 hand-off: send the clean frame + landmarks to a server engine.
   *
   * Inline engines (overlay) answer with the finished image. Queued engines
   * answer `pending` and are polled until the status goes terminal — see
   * docs/adr/0001-phase-2-inference-execution.md.
   */
  const handleGenerate = useCallback(async () => {
    const worn = useWardrobe.getState().wornItems();
    const garment = worn[worn.length - 1];
    if (!garment) {
      setAiError('Pick a garment first.');
      return;
    }
    const frame = grabFrame(false);
    if (!frame) return;

    const token = { abandoned: false };
    pollRef.current = token;
    setAiBusy(true);
    setAiError(null);

    const settle = (result: TryOnResult) => {
      setAiResult(result);
      if (result.status === 'failed') setAiError(result.error ?? 'Generation failed');
      if (result.output_url) setSnapshot(result.output_url);
    };

    try {
      let result = await api.tryOn({
        clothing_id: garment.id,
        person_image: frame.toDataURL('image/png'),
        engine,
        session_public_id: sessionId ?? undefined,
        pose_landmarks: tracker.landmarksRef.current
          ? { landmarks: tracker.landmarksRef.current }
          : undefined,
      });
      setAiResult(result);

      while (!isTerminal(result.status)) {
        if (token.abandoned) return;
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (token.abandoned) return;
        result = await api.tryOnResult(result.public_id);
        setAiResult(result);
      }
      settle(result);
    } catch (err) {
      if (!token.abandoned) {
        setAiError(err instanceof Error ? err.message : 'Try-on request failed');
      }
    } finally {
      if (!token.abandoned) setAiBusy(false);
      if (pollRef.current === token) pollRef.current = null;
    }
  }, [engine, grabFrame, sessionId, tracker.landmarksRef]);

  const handleCancelGenerate = useCallback(async () => {
    const pending = aiResult;
    if (!pending || isTerminal(pending.status)) return;
    try {
      setAiResult(await api.cancelTryOn(pending.public_id));
    } catch {
      /* the poll loop will pick up whatever actually happened */
    }
  }, [aiResult]);

  // Abandon any in-flight poll when the stage unmounts.
  useEffect(() => {
    return () => {
      if (pollRef.current) pollRef.current.abandoned = true;
    };
  }, []);

  const generating =
    aiBusy && aiResult != null && !isTerminal(aiResult.status) ? aiResult : null;

  const fpsTone = tracker.fps >= 30 ? 'good' : tracker.fps >= 18 ? 'warn' : 'bad';
  const busy = camera.status === 'requesting' || tracker.status === 'loading';

  return (
    <section className="flex h-full min-h-0 flex-col gap-3">
      <div className="glass relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        {/* Video + overlay share the same box; CSS mirroring keeps the math simple. */}
        <div className="relative flex h-full w-full items-center justify-center bg-black/45">
          <video
            ref={videoRef}
            playsInline
            muted
            autoPlay
            className={cn('h-full w-full object-contain', mirror && 'mirror-x')}
          />
          <canvas
            ref={canvasRef}
            className={cn(
              'pointer-events-none absolute inset-0 h-full w-full object-contain',
              mirror && 'mirror-x',
            )}
          />
        </div>

        {/* --- HUD --- */}
        <div className="pointer-events-none absolute left-4 top-4 flex flex-wrap items-center gap-2">
          <Pill tone={camera.status === 'live' ? 'good' : 'neutral'} pulse={camera.status === 'live'}>
            {camera.status === 'live' ? 'Camera live' : camera.status}
          </Pill>
          {showFps && camera.status === 'live' && (
            <>
              <Pill tone={fpsTone}>{tracker.fps.toFixed(0)} FPS</Pill>
              <Pill tone="neutral">{tracker.inferenceMs.toFixed(1)} ms pose</Pill>
            </>
          )}
          {camera.status === 'live' && (
            <Pill tone={tracker.bodyDetected ? 'accent' : 'warn'}>
              {tracker.bodyDetected ? 'Body tracked' : 'No body'}
            </Pill>
          )}
        </div>

        {camera.resolution && (
          <div className="pointer-events-none absolute right-4 top-4">
            <Pill tone="neutral">
              {camera.resolution.width}×{camera.resolution.height}
            </Pill>
          </div>
        )}

        {/* --- overlays for non-live states --- */}
        {busy && (
          <div className="absolute inset-0 grid place-items-center bg-ink-950/70 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/15 border-t-accent" />
              <p className="text-[13px] text-white/60">
                {camera.status === 'requesting' ? 'Waiting for camera…' : 'Loading pose model…'}
              </p>
            </div>
          </div>
        )}

        {(camera.status === 'denied' || camera.status === 'error' || camera.status === 'idle') &&
          !busy && (
            <div className="absolute inset-0 grid place-items-center bg-ink-950/85 p-8 text-center backdrop-blur">
              <div className="max-w-sm animate-fade-in">
                <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-white/8 text-2xl">
                  🎥
                </div>
                <h3 className="text-lg font-semibold">Camera is off</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-white/55">
                  {camera.error ?? 'Allow webcam access to start the virtual try-on.'}
                </p>
                <button type="button" onClick={() => void camera.start()} className="btn-primary mt-5">
                  Enable camera
                </button>
              </div>
            </div>
          )}

        {tracker.status === 'error' && (
          <div className="absolute bottom-20 left-1/2 max-w-md -translate-x-1/2 rounded-2xl border border-rose/25 bg-rose/12 px-4 py-3 text-[12px] text-rose backdrop-blur">
            {tracker.error}
          </div>
        )}

        {/* --- queued generation progress --- */}
        {generating && (
          <div className="absolute bottom-20 left-1/2 w-72 -translate-x-1/2 animate-fade-in rounded-2xl border border-white/10 bg-ink-900/85 px-4 py-3 backdrop-blur-xl">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] text-white/70">
                {generating.status === 'pending' ? 'Queued…' : `Generating · ${generating.engine}`}
              </span>
              <button
                type="button"
                onClick={() => void handleCancelGenerate()}
                className="text-[11px] text-white/40 transition hover:text-rose"
              >
                Cancel
              </button>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
              <div
                className={cn(
                  'h-full rounded-full bg-accent transition-[width] duration-300',
                  generating.progress <= 0 && 'animate-pulse-soft',
                )}
                style={{ width: `${Math.max(generating.progress * 100, 6)}%` }}
              />
            </div>
          </div>
        )}

        {/* --- control bar --- */}
        <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/10 bg-ink-900/70 p-1.5 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setPaused((p) => !p)}
            disabled={camera.status !== 'live'}
            className="btn-ghost border-0 bg-transparent px-3 py-1.5 text-xs hover:bg-white/10"
          >
            {paused ? '▶ Resume' : '❚❚ Pause'}
          </button>
          <div className="h-5 w-px bg-white/10" />
          <button
            type="button"
            onClick={handleSnapshot}
            disabled={camera.status !== 'live'}
            className="btn-primary px-4 py-1.5 text-xs"
          >
            Snapshot
          </button>
          <button
            type="button"
            onClick={() => void handleGenerate()}
            disabled={camera.status !== 'live' || aiBusy}
            title={
              engine === 'overlay'
                ? 'Render this frame server-side with the overlay engine'
                : `Generate with ${engine}`
            }
            className="btn-ghost border-0 bg-transparent px-3 py-1.5 text-xs hover:bg-white/10"
          >
            {aiBusy
              ? generating?.status === 'pending'
                ? 'Queued…'
                : 'Generating…'
              : `Generate · ${engine}`}
          </button>
          <div className="h-5 w-px bg-white/10" />
          <button
            type="button"
            onClick={() => (camera.status === 'live' ? camera.stop() : void camera.start())}
            className="btn-ghost border-0 bg-transparent px-3 py-1.5 text-xs hover:bg-white/10"
          >
            {camera.status === 'live' ? 'Stop' : 'Start'}
          </button>
        </div>
      </div>

      {/* --- camera picker + errors --- */}
      <div className="flex flex-wrap items-center gap-2">
        {camera.devices.length > 1 && (
          <select
            value={camera.deviceId ?? ''}
            onChange={(e) => void camera.selectDevice(e.target.value)}
            className="field max-w-xs"
          >
            {camera.devices.map((d) => (
              <option key={d.deviceId} value={d.deviceId} className="bg-ink-850">
                {d.label}
              </option>
            ))}
          </select>
        )}
        {aiError && (
          <span className="rounded-full border border-rose/25 bg-rose/10 px-3 py-1.5 text-[12px] text-rose">
            {aiError}
          </span>
        )}
        {aiResult?.status === 'completed' && (
          <span className="rounded-full border border-mint/25 bg-mint/10 px-3 py-1.5 text-[12px] text-mint">
            {aiResult.engine} · {aiResult.latency_ms ?? 0} ms
            {aiResult.cached ? ' · cached' : ''}
          </span>
        )}
        {aiResult?.status === 'cancelled' && (
          <span className="rounded-full border border-white/12 bg-white/5 px-3 py-1.5 text-[12px] text-white/50">
            Cancelled
          </span>
        )}
      </div>

      {/* --- snapshot preview --- */}
      {snapshot && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-6 backdrop-blur-md"
          onClick={() => setSnapshot(null)}
        >
          <div
            className="glass max-h-full w-full max-w-2xl animate-fade-in overflow-hidden p-3"
            onClick={(e) => e.stopPropagation()}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={snapshot} alt="Try-on result" className="max-h-[70vh] w-full rounded-2xl object-contain" />
            <div className="flex items-center justify-between gap-2 px-1 pt-3">
              <span className="text-[12px] text-white/45">
                {aiResult ? `Engine: ${aiResult.engine}` : 'Local composite'}
              </span>
              <div className="flex gap-2">
                <button type="button" onClick={() => setSnapshot(null)} className="btn-ghost text-xs">
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => downloadDataUrl(snapshot, `tryon-${Date.now()}.png`)}
                  className="btn-primary text-xs"
                >
                  Save PNG
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
