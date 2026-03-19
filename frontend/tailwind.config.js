/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        fin: {
          canvas: '#F6F1E8',
          surface: '#FBF8F2',
          panel: '#EFE7DA',
          border: '#D7CDBD',
          ink: '#1F2B2A',
          muted: '#70685C',
          accent: '#1F6A5A',
          accentStrong: '#154B40',
          accentSoft: '#DCE8E0',
          bronze: '#B58A57',
          success: '#3F7A5D',
          warning: '#A86A32',
          danger: '#A14B45',
          shadow: 'rgba(31, 43, 42, 0.12)',
        },
      },
      fontFamily: {
        sans: ['"Outfit"', '"Noto Sans JP"', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 24px 60px rgba(31, 43, 42, 0.08)',
        card: '0 14px 32px rgba(31, 43, 42, 0.08)',
      },
    },
  },
  plugins: [],
}
