import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        serif: ["Georgia", "ui-serif", "serif"],
      },
      colors: {
        ink: {
          50: "#f8f7f4",
          100: "#eeece5",
          200: "#d9d5c7",
          300: "#b9b19d",
          400: "#8c8472",
          500: "#635d4f",
          600: "#45413a",
          700: "#2c2a25",
          800: "#1a1916",
          900: "#0e0d0b",
        },
        saffron: {
          500: "#e07a2f",
          600: "#c06422",
        },
      },
    },
  },
  plugins: [],
};

export default config;
