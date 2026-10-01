import type { Config } from "tailwindcss";

// Palette: a cool lab-bench grey, navy ink, and two pen colours that identify the two readers everywhere they appear.
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Every colour is a CSS variable (app/globals.css) with a light and a dark value; "R G B" so /opacity works.
      colors: {
        bench: "rgb(var(--bench) / <alpha-value>)", sheet: "rgb(var(--sheet) / <alpha-value>)", paper: "rgb(var(--paper) / <alpha-value>)", track: "rgb(var(--track) / <alpha-value>)", select: "rgb(var(--select) / <alpha-value>)", strip: "rgb(var(--strip) / <alpha-value>)",
        ink: { DEFAULT: "rgb(var(--ink) / <alpha-value>)", soft: "rgb(var(--ink-soft) / <alpha-value>)" },
        muted: "rgb(var(--muted) / <alpha-value>)", rule: "rgb(var(--rule) / <alpha-value>)", hair: "rgb(var(--hair) / <alpha-value>)",
        primary: "rgb(var(--primary) / <alpha-value>)", "on-primary": "rgb(var(--on-primary) / <alpha-value>)",
        vlm: { DEFAULT: "rgb(var(--vlm) / <alpha-value>)", soft: "rgb(var(--vlm-soft) / <alpha-value>)" },
        ocr: { DEFAULT: "rgb(var(--ocr) / <alpha-value>)", soft: "rgb(var(--ocr-soft) / <alpha-value>)", text: "rgb(var(--ocr-text) / <alpha-value>)", light: "rgb(var(--ocr-light) / <alpha-value>)" },
        agree: { DEFAULT: "rgb(var(--agree) / <alpha-value>)", text: "rgb(var(--agree-text) / <alpha-value>)", soft: "rgb(var(--agree-soft) / <alpha-value>)" },
        warn: { DEFAULT: "rgb(var(--warn) / <alpha-value>)", text: "rgb(var(--warn-text) / <alpha-value>)", soft: "rgb(var(--warn-soft) / <alpha-value>)" },
        bad: { DEFAULT: "rgb(var(--bad) / <alpha-value>)", soft: "rgb(var(--bad-soft) / <alpha-value>)", text: "rgb(var(--bad-text) / <alpha-value>)" },
      },
      fontFamily: {
        // Self-hosted through @fontsource (imported in app/layout.tsx), so the app still works offline on the lab machine.
        sans: ['"IBM Plex Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        reading: ['"Source Serif 4"', '"Iowan Old Style"', "Charter", "Georgia", "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
