/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14232B",
        paper: "#F3F6F3",
        panel: "#FFFFFF",
        pine: { DEFAULT: "#0F5F52", dark: "#0A4A40", soft: "#DCEEE8" },
        line: "#D7DFDB",
        mute: "#5C6B67",
        amber: { ink: "#8A5A0B", soft: "#FBEFD5" },
        rust: { DEFAULT: "#B03A26", soft: "#FBE5E0" },
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ['"Instrument Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
