"use client";

// A segmented control: one pill, a sliding --edge indicator behind the active
// segment, active text in --ink, inactive in --muted. No buttons-in-a-row look.
// Sharp corners (border-radius:0 globally), 1px --edge frame.

export interface SegmentedOption {
  value: string;
  label: string;
}

export function Segmented({
  options,
  value,
  onChange,
}: {
  options: SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  const activeIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const pct = 100 / options.length;

  return (
    <div
      className="relative inline-flex border border-edge bg-void"
      role="tablist"
    >
      {/* Sliding indicator */}
      <span
        aria-hidden
        className="absolute inset-y-0 z-0 bg-edge transition-transform duration-200 ease-out"
        style={{
          width: `${pct}%`,
          transform: `translateX(${activeIndex * 100}%)`,
        }}
      />
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(o.value)}
            className="relative z-10 px-4 py-1.5 text-nav font-medium transition-colors"
            style={{ color: active ? "var(--ink)" : "var(--muted)" }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
