import type { Config } from "tailwindcss";

// Dark-only dashboard: the `tremor-*` design tokens are defined directly as dark
// values, so every Tremor component AND custom chrome renders on one coherent
// dark palette with no `dark:` plumbing. (dark-tremor mirrors it as a safety net.)
const darkPalette = {
  brand: {
    faint: "#171a2b", // subtle indigo-tinted fill for active states
    muted: "#312e81", // indigo-900
    subtle: "#4f46e5", // indigo-600
    DEFAULT: "#6366f1", // indigo-500 (accent)
    emphasis: "#a5b4fc", // indigo-300
    inverted: "#ffffff",
  },
  background: {
    muted: "#090a0f", // page background (darkest)
    subtle: "#171a22",
    DEFAULT: "#12141b", // card surface (elevated)
    emphasis: "#d1d5db",
  },
  border: { DEFAULT: "#23262f" },
  ring: { DEFAULT: "#2a2e3a" },
  content: {
    subtle: "#565d6b",
    DEFAULT: "#969db0", // secondary text
    emphasis: "#cdd3df",
    strong: "#f4f6fb", // headings / metrics
    inverted: "#090a0f",
  },
};

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
    "./node_modules/@tremor/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    transparent: "transparent",
    current: "currentColor",
    extend: {
      colors: {
        tremor: darkPalette,
        "dark-tremor": darkPalette,
      },
      boxShadow: {
        "tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.4)",
        "tremor-card": "0 1px 3px 0 rgb(0 0 0 / 0.5), 0 1px 2px -1px rgb(0 0 0 / 0.5)",
        "tremor-dropdown": "0 4px 12px -1px rgb(0 0 0 / 0.6), 0 2px 6px -2px rgb(0 0 0 / 0.5)",
        "dark-tremor-input": "0 1px 2px 0 rgb(0 0 0 / 0.4)",
        "dark-tremor-card": "0 1px 3px 0 rgb(0 0 0 / 0.5), 0 1px 2px -1px rgb(0 0 0 / 0.5)",
        "dark-tremor-dropdown": "0 4px 12px -1px rgb(0 0 0 / 0.6), 0 2px 6px -2px rgb(0 0 0 / 0.5)",
      },
      borderRadius: {
        "tremor-small": "0.375rem",
        "tremor-default": "0.75rem",
        "tremor-full": "9999px",
      },
      fontSize: {
        "tremor-label": ["0.75rem", { lineHeight: "1rem" }],
        "tremor-default": ["0.875rem", { lineHeight: "1.25rem" }],
        "tremor-title": ["1.125rem", { lineHeight: "1.75rem" }],
        "tremor-metric": ["1.875rem", { lineHeight: "2.25rem" }],
      },
    },
  },
  safelist: [
    {
      pattern:
        /^(bg-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(text-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(border-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
      variants: ["hover", "ui-selected"],
    },
    {
      pattern:
        /^(ring-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
    {
      pattern:
        /^(stroke-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
    {
      pattern:
        /^(fill-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(?:50|100|200|300|400|500|600|700|800|900|950))$/,
    },
  ],
  plugins: [],
};

export default config;
