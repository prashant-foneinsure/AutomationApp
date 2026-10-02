import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build output goes to ../static because FastAPI serves that directory
// with app.mount("/", StaticFiles(directory="static")). emptyOutDir is
// explicit because outDir is outside the project root -- Vite would otherwise
// refuse to clear it and stale hashed assets would accumulate.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    // Dev server proxies the API to the FastAPI process, so the frontend and
    // backend can be restarted independently while developing.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
})
