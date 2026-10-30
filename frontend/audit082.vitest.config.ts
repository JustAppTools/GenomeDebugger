import {defineConfig} from 'vitest/config'
import react from '@vitejs/plugin-react'
export default defineConfig({plugins:[react()],test:{environment:'jsdom',setupFiles:['./src/test-setup.ts'],include:['audit/v082.probe.tsx']}})
