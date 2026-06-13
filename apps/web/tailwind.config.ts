import type { Config } from "tailwindcss";

// Aryx brand palette — derived from the logo:
//   - navy gradient on the wolf shield (deep → mid → accent)
//   - off-white background, cream pull for hero surfaces
//   - sparing gold for highlight states (not in logo; complementary)
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Aryx navy — the wordmark + wolf colour.
        navy: {
          50: "#F2F5FB",
          100: "#E4EAF4",
          200: "#C2CFE3",
          300: "#94A8CB",
          400: "#5F7BAA",
          500: "#3A578C",
          600: "#27416E",
          700: "#1A2F55",
          800: "#0F1F3D",
          900: "#0A1530",
          950: "#050B1C",
        },
        // Accent blue — the lighter gradient stop on the wolf.
        steel: {
          400: "#5F8AD2",
          500: "#4068A8",
          600: "#2D4B8A",
        },
        // Background tones.
        canvas: "#F8F9FC",
        ink: "#0F1726",
        subtle: "#5A6478",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        wordmark: "0.32em",
      },
      maxWidth: {
        prose: "68ch",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(10, 21, 48, 0.04), 0 8px 24px rgba(10, 21, 48, 0.06)",
        glow: "0 0 0 1px rgba(64, 104, 168, 0.18), 0 8px 32px rgba(64, 104, 168, 0.18)",
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out both",
        "rise": "rise 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        rise: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
