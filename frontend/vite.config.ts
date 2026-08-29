import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Java 后端接口路由
      '/api/stock': {
        target: 'http://localhost:8879',
        changeOrigin: true,
      },
      '/api/market': {
        target: 'http://localhost:8879',
        changeOrigin: true,
      },
      '/api/watchlist': {
        target: 'http://localhost:8879',
        changeOrigin: true,
      },
      '/api/monitor': {
        target: 'http://localhost:8879',
        changeOrigin: true,
      },
      // Python 服务接口路由（聊天、数据同步、行情等）
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
