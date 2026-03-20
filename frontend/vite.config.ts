import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8080'
const backendProxy = {
  '/api': {
    target: apiProxyTarget,
    changeOrigin: true,
  },
  '/ready': {
    target: apiProxyTarget,
    changeOrigin: true,
  },
  '/health': {
    target: apiProxyTarget,
    changeOrigin: true,
  },
}

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['e2e/**', '**/node_modules/**'],
  },
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: backendProxy,
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
    proxy: backendProxy,
  },
})
