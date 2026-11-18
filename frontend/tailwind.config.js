/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f7f4ee',
          100: '#ece4d3',
          500: '#b08d57',
          700: '#7a5b2e',
          900: '#1a1714'
        }
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(176,141,87,0.25), 0 10px 30px rgba(0,0,0,0.25)'
      }
    },
  },
  plugins: [],
}
