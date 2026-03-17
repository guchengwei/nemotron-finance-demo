/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
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
