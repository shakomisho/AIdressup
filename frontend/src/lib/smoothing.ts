/**
 * Landmark smoothing.
 *
 * Raw BlazePose output jitters by a few pixels every frame, which reads as
 * "vibrating clothes". A One Euro filter removes that jitter while keeping fast
 * motion responsive (unlike a plain EMA, which has to trade one for the other).
 */
import type { Landmark } from './types';

class LowPass {
  private value: number | null = null;

  filter(x: number, alpha: number): number {
    this.value = this.value === null ? x : alpha * x + (1 - alpha) * this.value;
    return this.value;
  }

  get last(): number | null {
    return this.value;
  }

  reset(): void {
    this.value = null;
  }
}

class OneEuro {
  private x = new LowPass();
  private dx = new LowPass();
  private lastTime: number | null = null;

  constructor(
    private minCutoff = 1.0,
    private beta = 0.007,
    private dCutoff = 1.0,
  ) {}

  private static alpha(cutoff: number, dt: number): number {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(value: number, timestamp: number): number {
    const dt = this.lastTime === null ? 1 / 30 : Math.max((timestamp - this.lastTime) / 1000, 1e-3);
    this.lastTime = timestamp;

    const prev = this.x.last ?? value;
    const derivative = (value - prev) / dt;
    const edx = this.dx.filter(derivative, OneEuro.alpha(this.dCutoff, dt));
    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    return this.x.filter(value, OneEuro.alpha(cutoff, dt));
  }

  setParams(minCutoff: number, beta: number): void {
    this.minCutoff = minCutoff;
    this.beta = beta;
  }

  reset(): void {
    this.x.reset();
    this.dx.reset();
    this.lastTime = null;
  }
}

export class PoseSmoother {
  private filters: { x: OneEuro; y: OneEuro; z: OneEuro }[] = [];

  /** @param strength 0 = raw landmarks, 1 = heavily damped. */
  constructor(private strength = 0.6) {}

  setStrength(strength: number): void {
    this.strength = strength;
    const { minCutoff, beta } = this.params();
    for (const f of this.filters) {
      f.x.setParams(minCutoff, beta);
      f.y.setParams(minCutoff, beta);
      f.z.setParams(minCutoff, beta);
    }
  }

  /** Map 0..1 UI strength onto One Euro cutoffs. */
  private params(): { minCutoff: number; beta: number } {
    const s = Math.min(Math.max(this.strength, 0), 1);
    return {
      // More smoothing => lower cutoff frequency.
      minCutoff: 6.0 - 5.6 * s,
      beta: 0.02 + 0.05 * s,
    };
  }

  reset(): void {
    for (const f of this.filters) {
      f.x.reset();
      f.y.reset();
      f.z.reset();
    }
  }

  apply(landmarks: Landmark[], timestamp: number): Landmark[] {
    if (this.strength <= 0.001) return landmarks;
    const { minCutoff, beta } = this.params();
    while (this.filters.length < landmarks.length) {
      this.filters.push({
        x: new OneEuro(minCutoff, beta),
        y: new OneEuro(minCutoff, beta),
        z: new OneEuro(minCutoff, beta),
      });
    }
    return landmarks.map((l, i) => {
      const f = this.filters[i];
      return {
        x: f.x.filter(l.x, timestamp),
        y: f.y.filter(l.y, timestamp),
        z: f.z.filter(l.z, timestamp),
        visibility: l.visibility,
      };
    });
  }
}

/** Rolling FPS meter with a short window so the readout stays responsive. */
export class FpsMeter {
  private times: number[] = [];
  private total = 0;
  private frames = 0;

  tick(now = performance.now()): number {
    this.times.push(now);
    this.frames += 1;
    while (this.times.length > 1 && now - this.times[0] > 1000) this.times.shift();
    const fps = this.times.length > 1
      ? ((this.times.length - 1) * 1000) / (now - this.times[0])
      : 0;
    this.total += fps;
    return fps;
  }

  get average(): number {
    return this.frames ? this.total / this.frames : 0;
  }

  get frameCount(): number {
    return this.frames;
  }

  reset(): void {
    this.times = [];
    this.total = 0;
    this.frames = 0;
  }
}
