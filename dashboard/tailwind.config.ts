import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Channel triples + <alpha-value> so `bg-surface/95` and `border-signal/40`
        // actually compile. Hex values make Tailwind drop those classes entirely.
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        "ink-2": "rgb(var(--ink-2) / <alpha-value>)",
        "ink-3": "rgb(var(--ink-3) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        "signal-ink": "rgb(var(--signal-ink) / <alpha-value>)",
        moss: "rgb(var(--moss) / <alpha-value>)",
        ochre: "rgb(var(--ochre) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        // Hairlines are always used at their default weight, so the alpha lives in
        // the token itself.
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ['"Bricolage Grotesque"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "Consolas", "monospace"],
      },
      borderRadius: {
        cell: "4px",
        stamp: "2px",
      },
      maxWidth: {
        shell: "1120px",
      },
      keyframes: {
        "rise-in": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.86)" },
        },
      },
      animation: {
        "rise-in": "rise-in 420ms cubic-bezier(.2,.8,.2,1) both",
        "pulse-dot": "pulse-dot 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;