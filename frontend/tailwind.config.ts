import type { Config } from "tailwindcss";

// Palette: a cool lab-bench grey, navy ink, and two pen colours that identify the two readers everywhere they appear.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bench: "#E8ECF0",
        sheet: "#F7F9FA",
        ink: "#16233A",
        muted: "#5B6B7B",
        rule: "#C5CDD6",
        vlm: { DEFAULT: "#0B7A75", soft: "#DDF0EE" },
        ocr: { DEFAULT: "#A8580C", soft: "#F7E7D3" },
        agree: "#2F7D4F",
        warn: "#9A6700",
        bad: { DEFAULT: "#B42318", soft: "#FBE4E1" },
      },
      fontFamily: {
        // System stacks only: the app has to work offline on the lab machine.
        sans: ['"Segoe UI"', "system-ui", "-apple-system", "Roboto", "sans-serif"],
        reading: ['"Iowan Old Style"', "Charter", "Georgia", "Cambria", "serif"],
      },
    },
  },
  plugins: [],
};
export default config;
