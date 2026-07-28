import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './styles/global.css'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { installSessionExpiryHandler } from './api/session-expiry'

async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)

  const auth = useAuthStore(pinia)
  await auth.restoreSession()
  installSessionExpiryHandler(async (redirect) => {
    auth.logout()
    window.dispatchEvent(new CustomEvent('studypilot:session-expired'))
    const safeRedirect = redirect.startsWith('/') && !redirect.startsWith('/login')
      ? redirect
      : '/dashboard'
    await router.replace({ name: 'login', query: { redirect: safeRedirect } })
    ElMessage.error('登录状态已失效，请重新登录')
  })

  app.use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
}

void bootstrap()
