import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#E8F4FD",
          100: "#C5E3F9",
          200: "#9DD0F5",
          300: "#6DB9EF",
          400: "#3FA2E8",
          500: "#2E86AB",  // brand blue
          600: "#256D8C",
          700: "#1C546D",
          800: "#143B4E",
          900: "#0B222F",
        },
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#EF4444",
      },
    },
  },
  plugins: [],
};

export default config;
