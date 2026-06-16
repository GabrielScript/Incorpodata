import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// O frontend chama /api/* relativo; em dev o Vite faz proxy pro FastAPI (8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
