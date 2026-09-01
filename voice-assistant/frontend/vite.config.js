import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

/**
 * Vite 配置
 *
 * 环境变量优先级（高→低）：
 *   1. 系统环境变量（如 VITE_WS_URL=xxx npm run dev）
 *   2. .env.[mode].local 文件
 *   3. .env.[mode] 文件
 *   4. .env 文件
 *
 * 可用的环境变量（定义在 .env 文件中）：
 *   VITE_API_URL     - 后端 HTTP 地址（默认 http://localhost:8000）
 *   VITE_WS_URL      - 后端 WebSocket 地址（默认 ws://localhost:8000）
 *   VITE_APP_TITLE   - 应用标题
 */
export default defineConfig(({ mode }) => {
  // 加载环境变量（mode = development / production）
  const env = loadEnv(mode, process.cwd(), '')

  // 从环境变量读取后端地址，带默认值
  const apiTarget = env.VITE_API_URL || 'http://localhost:8000'
  // 代理目标统一用 HTTP 地址，不读取 VITE_WS_URL（那是前端连接地址，不是代理目标）
  const backendTarget = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [vue()],

    // 路径别名：@ → src/
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },

    // 开发服务器配置
    server: {
      port: 3000,
      host: '0.0.0.0', // 允许局域网访问
      strictPort: false, // 端口被占用时自动递增
      open: false, // 不自动打开浏览器

      // 代理配置：将前端请求转发到后端
      proxy: {
        // HTTP API 代理
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // 超时设置（毫秒）
          timeout: 30000,
          // 代理请求头优化
          configure: proxy => {
            proxy.on('error', err => {
              console.error('[vite proxy] /api 代理错误:', err.message)
            })
          }
        },

        // WebSocket 代理
        '/ws': {
          target: backendTarget,
          ws: true, // 启用 WebSocket 代理
          changeOrigin: true,
          configure: proxy => {
            let warned = false
            proxy.on('error', err => {
              if (!warned) {
                warned = true
                console.error('[vite proxy] /ws 代理错误:', err.message, '（后续错误已抑制）')
              }
            })
          }
        }
      }
    },

    // 构建配置
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: false, // 生产环境不生成 sourcemap
      // 构建产物大小警告阈值（kB）
      chunkSizeWarningLimit: 500,
      rollupOptions: {
        output: {
          // 将依赖拆分为更小的 chunk
          manualChunks: {
            vendor: ['vue']
          }
        }
      }
    },

    // 环境变量目录（默认即为项目根目录，显式声明更清晰）
    envDir: resolve(__dirname),

    // 环境变量白名单：只有 VITE_ 前缀的变量才会暴露给客户端
    envPrefix: 'VITE_'
  }
})
