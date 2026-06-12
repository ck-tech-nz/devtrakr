import { readFileSync, existsSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { resolve } from 'node:path'

declare const process: { env: Record<string, string | undefined> }
const apiBase = process.env.NUXT_API_BASE || 'http://localhost:8000'
const minioBase = process.env.NUXT_MINIO_BASE || 'http://121.31.38.35:19000/devtrack-uploads'

function getBuildInfo() {
  const versionFile = resolve(__dirname, 'VERSION')
  if (existsSync(versionFile)) {
    const content = readFileSync(versionFile, 'utf-8').trim()
    // VERSION written by CI: "env/prod abc1234"(两段式: 环境 + 短 SHA,日期已去除以便镜像层按 SHA 复用)
    const parts = content.split(' ')
    const gitHash = parts[parts.length - 1]
    // 构建日期不再来自 VERSION:nuxt build 就在 CI 构建时执行,取当时日期即构建日期
    const buildDate = new Date().toISOString().slice(0, 10)
    return { version: content, gitHash, buildDate }
  }
  try {
    const gitHash = execSync('git rev-parse --short HEAD', { encoding: 'utf-8' }).trim()
    return { version: `dev ${gitHash}`, gitHash, buildDate: null }
  } catch {
    return { version: 'dev', gitHash: null, buildDate: null }
  }
}

const buildInfo = getBuildInfo()
const pkg = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf-8'))
const nuxtVersion = pkg.dependencies?.nuxt?.replace(/^\^/, '') || ''
const vueVersion = pkg.dependencies?.vue?.replace(/^\^/, '') || ''

export default defineNuxtConfig({
  ssr: false,
  devtools: { enabled: false },
  devServer: { port: Number(process.env.NUXT_PORT) || 3004 },
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  colorMode: { preference: 'light', fallback: 'light' },
  runtimeConfig: {
    public: {
      version: buildInfo.version,
      gitHash: buildInfo.gitHash || '',
      buildDate: buildInfo.buildDate || '',
      nuxtVersion,
      vueVersion,
      serverMonitorUrl: '',
    },
  },
  app: {
    baseURL: '/',
    head: {
      title: 'DevTrakr - 项目管理平台',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover' },
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
      ],
    },
  },
  routeRules: {
    '/api/**': { proxy: `${apiBase}/api/**` },
    '/uploads/**': { proxy: `${minioBase}/**` },
  },
  nitro: {
    devProxy: {
      '/api/': {
        target: `${apiBase}/api/`,
        changeOrigin: true,
      },
      '/uploads/': {
        target: `${minioBase}/`,
        changeOrigin: true,
      },
    },
  },
  compatibilityDate: '2025-01-01',
})
