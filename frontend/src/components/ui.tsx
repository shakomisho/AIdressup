/** Small Apple-flavoured control set: toggle, slider, segmented picker, pill. */
'use client';

import { cn } from '@/lib/utils';

export function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label
      className={cn(
        'flex items-center justify-between gap-3 rounded-2xl px-3 py-2.5 transition-colors',
        disabled ? 'opacity-40' : 'hover:bg-white/[0.045]',
      )}
    >
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium text-white/85">{label}</span>
        {hint && <span className="block truncate text-[11px] text-white/40">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-[26px] w-[44px] shrink-0 rounded-full transition-colors duration-300',
          checked ? 'bg-mint' : 'bg-white/15',
        )}
      >
        <span
          className={cn(
            'absolute top-[3px] h-5 w-5 rounded-full bg-white shadow-lift transition-transform duration-300',
            checked ? 'translate-x-[21px]' : 'translate-x-[3px]',
          )}
        />
      </button>
    </label>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 0.01,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  format?: (value: number) => string;
  onChange: (value: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="px-3 py-2">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[13px] font-medium text-white/85">{label}</span>
        <span className="font-mono text-[11px] text-white/45">
          {format ? format(value) : value.toFixed(2)}
        </span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ backgroundSize: `${pct}% 100%` }}
      />
    </div>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="px-3 py-2">
      {label && <div className="mb-2 text-[13px] font-medium text-white/85">{label}</div>}
      <div className="flex gap-1 rounded-2xl bg-white/[0.06] p-1">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            title={opt.hint}
            onClick={() => onChange(opt.value)}
            className={cn(
              'flex-1 rounded-xl px-2 py-1.5 text-[12px] font-medium transition-all duration-200',
              value === opt.value
                ? 'bg-white/90 text-ink-900 shadow-lift'
                : 'text-white/55 hover:text-white/85',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Pill({
  tone = 'neutral',
  children,
  pulse,
}: {
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'accent';
  children: React.ReactNode;
  pulse?: boolean;
}) {
  const tones = {
    neutral: 'bg-white/8 text-white/65 border-white/10',
    good: 'bg-mint/15 text-mint border-mint/25',
    warn: 'bg-amber/15 text-amber border-amber/25',
    bad: 'bg-rose/15 text-rose border-rose/25',
    accent: 'bg-accent/15 text-accent-soft border-accent/30',
  } as const;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
        tones[tone],
      )}
    >
      {pulse && <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function SectionCard({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('glass p-3', className)}>
      <header className="mb-1.5 flex items-center justify-between gap-2 px-1">
        <h2 className="panel-title">{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}
