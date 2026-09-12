#!/usr/bin/env node
/**
 * Vendors MediaPipe so the app runs fully offline:
 *   1. copies the tasks-vision WASM bundle from node_modules -> public/mediapipe
 *   2. downloads the Pose Landmarker .task models -> public/models
 *
 * Runs automatically after `npm install`. Re-run any time: `npm run setup`.
 * Network failures are non-fatal — the app falls back to the jsDelivr CDN.
 */
import { createWriteStream } from 'node:fs';
import { cp, mkdir, stat, readdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const quiet = process.argv.includes('--quiet');
const log = (...args) => !quiet && console.log(...args);

const MODELS = [
  {
    name: 'pose_landmarker_lite.task',
    url: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
  },
  {
    name: 'pose_landmarker_full.task',
    url: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task',
  },
  {
    name: 'pose_landmarker_heavy.task',
    url: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task',
  },
];

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

async function copyWasm() {
  const src = join(root, 'node_modules', '@mediapipe', 'tasks-vision', 'wasm');
  const dest = join(root, 'public', 'mediapipe');
  if (!(await exists(src))) {
    log('! @mediapipe/tasks-vision not installed yet — skipping wasm copy');
    return false;
  }
  await mkdir(dest, { recursive: true });
  await cp(src, dest, { recursive: true });
  const files = await readdir(dest);
  log(`✓ wasm bundle -> public/mediapipe (${files.length} files)`);
  return true;
}

async function download({ name, url }) {
  const dest = join(root, 'public', 'models', name);
  if (await exists(dest)) {
    log(`· ${name} already present`);
    return true;
  }
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(120_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await mkdir(dirname(dest), { recursive: true });
    await pipeline(Readable.fromWeb(res.body), createWriteStream(dest));
    const { size } = await stat(dest);
    log(`✓ ${name} (${(size / 1024 / 1024).toFixed(1)} MB)`);
    return true;
  } catch (err) {
    log(`! ${name} download failed (${err.message}) — CDN fallback will be used`);
    return false;
  }
}

const wasmOk = await copyWasm();
const results = await Promise.all(MODELS.map(download));
if (!quiet) {
  const ok = results.filter(Boolean).length;
  log(`\nMediaPipe assets: wasm ${wasmOk ? 'ok' : 'missing'}, models ${ok}/${MODELS.length}`);
}
