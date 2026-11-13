/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        nav: { DEFAULT: "#101827", 800: "#18233A", 700: "#223050", line: "#2A3755", text: "#C9D3E3", muted: "#8E9BB3" },
        canvas: "#F5F7FA",
        panel: "#FFFFFF",
        ink: { DEFAULT: "#172033", 2: "#5E6B7E", 3: "#6B7789" },
        line: { DEFAULT: "#DDE3EA", soft: "#E9EDF2", strong: "#C7D0DB" },
        accent: { DEFAULT: "#087F8C", 600: "#076F7B", 700: "#066A75", 50: "#E8F4F5", 100: "#CDE8EB", 300: "#5DB3BC" },
        warn: { DEFAULT: "#A65D00", 50: "#FBF2E6", 100: "#F5E0C2" },
        crit: { DEFAULT: "#C93644", 50: "#FDF1F2", 100: "#F5CDD2" },
        ok: { DEFAULT: "#18794E", 50: "#E8F4EE", 100: "#C8E5D5" },
        sim: { DEFAULT: "#5B4BA8", 50: "#F0EEFA" },
        lab: { DEFAULT: "#0B6E4F", 50: "#E6F3EE" },
        imp: { DEFAULT: "#7A5A12", 50: "#F7F1E3" },
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", { lineHeight: "1rem" }] },
      boxShadow: {
        panel: "0 1px 2px rgba(16,24,39,0.04), 0 1px 1px rgba(16,24,39,0.03)",
        lift: "0 6px 20px -6px rgba(16,24,39,0.18), 0 2px 6px -2px rgba(16,24,39,0.08)",
        focus: "0 0 0 3px rgba(8,127,140,0.35)",
      },
      keyframes: {
        pulseRing: { "0%": { boxShadow: "0 0 0 0 rgba(201,54,68,0.45)" }, "70%": { boxShadow: "0 0 0 6px rgba(201,54,68,0)" }, "100%": { boxShadow: "0 0 0 0 rgba(201,54,68,0)" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
        dash: { to: { strokeDashoffset: "0" } },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
      },
      animation: {
        pulseRing: "pulseRing 1.8s ease-out infinite",
        shimmer: "shimmer 1.4s linear infinite",
        blink: "blink 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
