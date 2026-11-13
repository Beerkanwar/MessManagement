import tailwindTheme from './src/design/tailwind-theme.js';

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: tailwindTheme.theme,
  plugins: [],
};

