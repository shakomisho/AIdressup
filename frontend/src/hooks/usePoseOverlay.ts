/**
 * The Phase 1 render loop.
 *
 * Per frame: MediaPipe Pose -> One Euro smoothing -> landmark solve -> canvas.
 * Driven by `requestVideoFrameCallback` when available (fires exactly once per
 * decoded camera frame, so we never run inference twice on the same image) and
 * falls back to `requestAnimationFrame`.
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { effectiveOverlay, solvePlacements } from '@/lib/anchors';
import { clear, drawGarment, drawSkeleton } from '@/lib/draw';
import { createPoseLandmarker, type PoseLandmarker } from '@/lib/pose';
import { FpsMeter, PoseSmoother } from '@/lib/smoothing';
import type { Landmark } from '@/lib/types';
import { useSettings } from '@/store/useSettings';
import { useWardrobe } from '@/store/useWardrobe';

export type TrackerStatus = 'idle' | 'loading' | 'running' | 'error';

interface Options {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  enabled: boolean;
}

interface Result {
  status: TrackerStatus;
  error: string | null;
  fps: number;
  avgFps: number;
  frames: number;
  bodyDetected: boolean;
  inferenceMs: number;
  /** Latest smoothed landmarks — handed to the backend with a snapshot. */
  landmarksRef: React.RefObject<Landmark[] | null>;
}

export function usePoseOverlay({ videoRef, canvasRef, enabled }: Options): Result {
  const [status, setStatus] = useState<TrackerStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const [avgFps, setAvgFps] = useState(0);
  const [frames, setFrames] = useState(0);
  const [bodyDetected, setBodyDetected] = useState(false);
  const [inferenceMs, setInferenceMs] = useState(0);

  const landmarkerRef = useRef<PoseLandmarker | null>(null);
  const landmarksRef = useRef<Landmark[] | null>(null);
  const smootherRef = useRef(new PoseSmoother(useSettings.getState().smoothing));
  const meterRef = useRef(new FpsMeter());
  const rafRef = useRef<number | null>(null);
  const vfcRef = useRef<number | null>(null);
  const lastTimestampRef = useRef(-1);
  const disposedRef = useRef(false);

  const modelVariant = useSettings((s) => s.modelVariant);
  const delegate = useSettings((s) => s.delegate);
  const smoothing = useSettings((s) => s.smoothing);

  useEffect(() => {
    smootherRef.current.setStrength(smoothing);
  }, [smoothing]);

  // ---- load / reload the landmarker when the model options change ---------
  useEffect(() => {
    let cancelled = false;
    disposedRef.current = false;
    setStatus('loading');
    setError(null);

    createPoseLandmarker({ variant: modelVariant, delegate })
      .then((landmarker) => {
        if (cancelled) {
          landmarker.close();
          return;
        }
        landmarkerRef.current?.close();
        landmarkerRef.current = landmarker;
        lastTimestampRef.current = -1;
        smootherRef.current.reset();
        setStatus('running');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus('error');
        setError(
          err instanceof Error
            ? `Pose model failed to load: ${err.message}`
            : 'Pose model failed to load.',
        );
      });

    return () => {
      cancelled = true;
      disposedRef.current = true;
      landmarkerRef.current?.close();
      landmarkerRef.current = null;
    };
  }, [modelVariant, delegate]);

  // ---- the loop ----------------------------------------------------------
  const renderFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const landmarker = landmarkerRef.current;
    if (!video || !canvas || !landmarker || video.readyState < 2) return;

    const { videoWidth: vw, videoHeight: vh } = video;
    if (!vw || !vh) return;
    if (canvas.width !== vw || canvas.height !== vh) {
      canvas.width = vw;
      canvas.height = vh;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // MediaPipe requires a strictly increasing timestamp in VIDEO mode.
    let timestamp = performance.now();
    if (timestamp <= lastTimestampRef.current) timestamp = lastTimestampRef.current + 1;
    lastTimestampRef.current = timestamp;

    const t0 = performance.now();
    let raw: Landmark[] | null = null;
    try {
      const result = landmarker.detectForVideo(video, timestamp);
      raw = (result.landmarks?.[0] as Landmark[] | undefined) ?? null;
    } catch {
      // A dropped frame is not worth tearing the session down.
      return;
    }
    const inference = performance.now() - t0;

    const settings = useSettings.getState();
    clear(ctx);

    if (raw) {
      const smoothed = smootherRef.current.apply(raw, timestamp);
      landmarksRef.current = smoothed;

      if (settings.showClothing) {
        const wardrobe = useWardrobe.getState();
        for (const item of wardrobe.wornItems()) {
          const sprite = wardrobe.sprites.get(item.id);
          if (!sprite?.complete || !sprite.naturalWidth) continue;
          const cfg = effectiveOverlay(item.overlay, settings);
          const placements = solvePlacements(
            smoothed,
            vw,
            vh,
            cfg,
            settings.visibilityThreshold,
          );
          if (placements.length) drawGarment(ctx, sprite, placements, cfg);
        }
      }

      if (settings.showSkeleton || settings.showLandmarks) {
        drawSkeleton(ctx, smoothed, vw, vh, {
          lines: settings.showSkeleton,
          dots: settings.showLandmarks,
          visibilityThreshold: settings.visibilityThreshold,
        });
      }
    } else {
      landmarksRef.current = null;
    }

    const measured = meterRef.current.tick();
    // React state updates are throttled to ~6 Hz; the loop itself is untouched.
    if (meterRef.current.frameCount % 5 === 0) {
      setFps(measured);
      setAvgFps(meterRef.current.average);
      setFrames(meterRef.current.frameCount);
      setInferenceMs(inference);
      setBodyDetected(Boolean(raw));
    }
  }, [canvasRef, videoRef]);

  useEffect(() => {
    const video = videoRef.current;
    if (!enabled || status !== 'running' || !video) return;

    let stopped = false;
    type VideoWithVFC = HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    };
    const v = video as VideoWithVFC;
    const useVfc = typeof v.requestVideoFrameCallback === 'function';

    const step = () => {
      if (stopped || disposedRef.current) return;
      renderFrame();
      if (useVfc) vfcRef.current = v.requestVideoFrameCallback!(step);
      else rafRef.current = requestAnimationFrame(step);
    };
    step();

    return () => {
      stopped = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      if (vfcRef.current !== null && v.cancelVideoFrameCallback) {
        v.cancelVideoFrameCallback(vfcRef.current);
      }
      rafRef.current = null;
      vfcRef.current = null;
    };
  }, [enabled, status, renderFrame, videoRef]);

  // Clear the canvas when tracking is paused so stale garments do not linger.
  useEffect(() => {
    if (enabled) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) clear(ctx);
    meterRef.current.reset();
    smootherRef.current.reset();
  }, [enabled, canvasRef]);

  return { status, error, fps, avgFps, frames, bodyDetected, inferenceMs, landmarksRef };
}
