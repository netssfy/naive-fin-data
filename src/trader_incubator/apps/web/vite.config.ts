import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

const seasonsRoot = path.resolve(__dirname, '../../core/skills/seasons')

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@seasons': seasonsRoot,
    },
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, '../..'), '.'],
    },

  },
})
