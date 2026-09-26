/**
 * Webcam lifecycle: permission, device enumeration, stream start/stop.
 * The stream is attached to the passed <video> element and cleaned up on unmount.
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type CameraStatus = 'idle' | 'requesting' | 'live' | 'denied' | 'error';

export interface CameraDevice {
  deviceId: string;
  label: string;
}

interface UseWebcamResult {
  status: CameraStatus;
  error: string | null;
  devices: CameraDevice[];
  deviceId: string | null;
  resolution: { width: number; height: number } | null;
  start: (deviceId?: string) => Promise<void>;
  stop: () => void;
  selectDevice: (deviceId: string) => Promise<void>;
}

const CONSTRAINTS: MediaTrackConstraints = {
  width: { ideal: 1280 },
  height: { ideal: 720 },
  frameRate: { ideal: 30, max: 60 },
};

export function useWebcam(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  { autoStart = true }: { autoStart?: boolean } = {},
): UseWebcamResult {
  const [status, setStatus] = useState<CameraStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState<CameraDevice[]>([]);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [resolution, setResolution] = useState<{ width: number; height: number } | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // `getUserMedia` cannot be cancelled. This token makes a response from a
  // previous start (including React Strict Mode's development remount) harmless.
  const requestRef = useRef(0);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    setDevices(
      all
        .filter((d) => d.kind === 'videoinput')
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Camera ${i + 1}` })),
    );
  }, []);

  const stop = useCallback(() => {
    requestRef.current += 1;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setStatus('idle');
    setResolution(null);
  }, [videoRef]);

  const start = useCallback(
    async (requestedId?: string) => {
      if (!window.isSecureContext) {
        setStatus('error');
        setError('Camera access requires HTTPS, or opening this app on localhost.');
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('error');
        setError('This browser does not expose getUserMedia. Use Chrome, Edge or Safari.');
        return;
      }
      const requestId = ++requestRef.current;
      setStatus('requesting');
      setError(null);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: requestedId
            ? { ...CONSTRAINTS, deviceId: { exact: requestedId } }
            : { ...CONSTRAINTS, facingMode: 'user' },
          audio: false,
        });
        if (requestId !== requestRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play().catch(() => undefined);
        }
        const track = stream.getVideoTracks()[0];
        const s = track?.getSettings();
        setDeviceId(s?.deviceId ?? requestedId ?? null);
        setResolution(
          s?.width && s?.height ? { width: s.width, height: s.height } : null,
        );
        setStatus('live');
        await refreshDevices(); // labels are only exposed after permission
      } catch (err) {
        if (requestId !== requestRef.current) return;
        const name = err instanceof DOMException ? err.name : '';
        if (name === 'NotAllowedError' || name === 'SecurityError') {
          setStatus('denied');
          setError('Camera permission denied. Allow access in the browser site settings.');
        } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
          setStatus('error');
          setError('No camera matched the requested settings.');
        } else {
          setStatus('error');
          setError(err instanceof Error ? err.message : 'Unable to open the camera.');
        }
      }
    },
    [refreshDevices, videoRef],
  );

  const selectDevice = useCallback(
    async (id: string) => {
      setDeviceId(id);
      await start(id);
    },
    [start],
  );

  useEffect(() => {
    if (autoStart) void start();
    return () => {
      requestRef.current += 1;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    navigator.mediaDevices?.addEventListener?.('devicechange', refreshDevices);
    return () => navigator.mediaDevices?.removeEventListener?.('devicechange', refreshDevices);
  }, [refreshDevices]);

  return { status, error, devices, deviceId, resolution, start, stop, selectDevice };
}
