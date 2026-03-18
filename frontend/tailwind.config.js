/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        fin: {
          primary: '#2563EB',    // Professional blue for CTAs
          secondary: '#0EA5E9',  // Sky blue for secondary elements
          dark: '#0F172A',       // Deep slate navy background
          darker: '#1E293B',     // Card/panel background
          surface: '#1E2D40',    // Elevated surface
          border: 'rgba(71, 130, 181, 0.15)',  // Subtle blue border
          success: '#059669',    // Emerald green
          warning: '#D97706',    // Amber
          danger: '#DC2626',     // Red
        },
        // Keep nvidia for backwards compatibility during transition
        nvidia: {
          green: '#76B900',
          blue: '#00A3E0',
          dark: '#0a0a0f',
          darker: '#141420',
          surface: '#1c1c2e',
          border: 'rgba(118,185,0,0.15)',
        },
      },
      fontFamily: {
        sans: ['"Noto Sans JP"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
