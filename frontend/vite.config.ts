import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In development there are two servers: React here on 5173, FastAPI on
    // 8000. A browser refuses to let a page served by one port fetch from
    // another — that rule is called CORS, and it exists for good reasons.
    //
    // We could switch it off on the backend, but that means loosening a real
    // security rule to fix a local inconvenience. Instead, Vite forwards
    // anything starting with /api on to FastAPI.
    //
    // The payoff: our React code says fetch("/api/status") — exactly what it
    // will say in production, where one server serves both. Nothing has to
    // change when we bundle them together in Step 6.6.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
