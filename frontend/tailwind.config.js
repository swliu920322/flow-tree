/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        'breathing': 'pulseGlow 2s infinite ease-in-out',
        'alert': 'alertFlash 1.5s infinite ease-in-out',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 15px rgba(234, 179, 8, 0.4)' },
          '50%': { boxShadow: '0 0 30px rgba(234, 179, 8, 0.8)' },
        },
        alertFlash: {
          '0%, 100%': { boxShadow: '0 0 10px rgba(239, 68, 68, 0.5)' },
          '50%': { boxShadow: '0 0 25px rgba(239, 68, 68, 0.9)' },
        },
      },
    },
  },
  plugins: [],
}
