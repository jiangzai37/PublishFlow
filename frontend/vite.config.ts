import { resolve } from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(__dirname, '..'), '')
  const backendHost = !env.APP_HOST || ['0.0.0.0', '::'].includes(env.APP_HOST)
    ? '127.0.0.1'
    : env.APP_HOST
  const backendPort = env.APP_PORT || '8765'
  const proxy = {
    '/api': `http://${backendHost}:${backendPort}`,
    '/media': `http://${backendHost}:${backendPort}`,
    '/videos': `http://${backendHost}:${backendPort}`,
    '/assets': `http://${backendHost}:${backendPort}`,
  }

  return {
    plugins: [vue()],
    server: {
      host: env.FRONTEND_HOST || '127.0.0.1',
      port: Number(env.FRONTEND_PORT || 5173),
      strictPort: true,
      proxy,
    },
    preview: {
      host: env.FRONTEND_HOST || '127.0.0.1',
      port: Number(env.FRONTEND_PORT || 5173),
      strictPort: true,
      proxy,
    },
  }
})
