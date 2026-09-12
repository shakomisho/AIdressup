/**
 * MediaPipe Pose Landmarker bootstrap.
 *
 * Assets are vendored locally by `npm run setup` (public/mediapipe +
 * public/models) so the app works offline; if a local file is missing we fall
 * back to the official CDN. GPU delegate is the default — it is what makes
 * 30+ FPS achievable; CPU is the fallback for machines without WebGL2.
 */
import { FilesetResolver, PoseLandmarker } from '@mediapipe/tasks-vision';

export type ModelVariant = 'lite' | 'full' | 'heavy';
export type Delegate = 'GPU' | 'CPU';

const CDN_WASM =
  'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.22/wasm';
const CDN_MODEL = (variant: ModelVariant) =>
  `https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_${variant}/float16/1/pose_landmarker_${variant}.task`;

const LOCAL_WASM = '/mediapipe';
const LOCAL_MODEL = (variant: ModelVariant) => `/models/pose_landmarker_${variant}.task`;

async function headOk(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok;
  } catch {
    return false;
  }
}

let filesetPromise: Promise<Awaited<ReturnType<typeof FilesetResolver.forVisionTasks>>> | null =
  null;

async function getFileset() {
  if (!filesetPromise) {
    filesetPromise = (async () => {
      const local = await headOk(`${LOCAL_WASM}/vision_wasm_internal.js`);
      return FilesetResolver.forVisionTasks(local ? LOCAL_WASM : CDN_WASM);
    })();
  }
  return filesetPromise;
}

export interface PoseOptions {
  variant: ModelVariant;
  delegate: Delegate;
  numPoses?: number;
  minPoseDetectionConfidence?: number;
  minTrackingConfidence?: number;
}

/**
 * Set once the GPU delegate has proven unavailable. Every reload (model swap,
 * remount) would otherwise repeat the same failing WebGL handshake and spam
 * the console with MediaPipe's `kGpuService` trace.
 */
let gpuUnavailable = false;

export function isGpuUnavailable(): boolean {
  return gpuUnavailable;
}

export async function createPoseLandmarker(opts: PoseOptions): Promise<PoseLandmarker> {
  const vision = await getFileset();
  const localModel = LOCAL_MODEL(opts.variant);
  const modelAssetPath = (await headOk(localModel)) ? localModel : CDN_MODEL(opts.variant);
  const delegate = gpuUnavailable ? 'CPU' : opts.delegate;

  try {
    return await PoseLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath, delegate },
      runningMode: 'VIDEO',
      numPoses: opts.numPoses ?? 1,
      minPoseDetectionConfidence: opts.minPoseDetectionConfidence ?? 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: opts.minTrackingConfidence ?? 0.5,
      outputSegmentationMasks: false,
    });
  } catch (err) {
    if (delegate === 'GPU') {
      // WebGL unavailable (VM, blocklisted driver) — retry on CPU and remember.
      gpuUnavailable = true;
      return createPoseLandmarker({ ...opts, delegate: 'CPU' });
    }
    throw err;
  }
}

export { PoseLandmarker };
