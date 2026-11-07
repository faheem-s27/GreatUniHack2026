import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // ws: true also carries the live captions socket (/api/ws/captions/...)
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
      // Live lecture room WebSocket (backend/live.py)
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
