import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// fs.allow lets fixtures mode (VITE_API_BASE=fixtures) read ../contract/fixtures directly.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, fs: { allow: ['..'] } },
})
