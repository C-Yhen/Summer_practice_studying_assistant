<script setup lang="ts">
import { reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, Message } from '@element-plus/icons-vue'
import AppLogo from '@/components/AppLogo.vue'
import AuthShowcase from '@/components/AuthShowcase.vue'
import { useAuthStore } from '@/stores/auth'
import { ref } from 'vue'
import { getApiErrorMessage, mockEnabled } from '@/api/client'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const formRef = ref<FormInstance>()
const form = reactive({
  email: mockEnabled ? 'demo@studypilot.cn' : '',
  password: mockEnabled ? 'Demo@123456' : '',
})
const rules: FormRules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (!await formRef.value?.validate().catch(() => false)) return
  try {
    await auth.login(form.email, form.password)
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
      ? route.query.redirect
      : '/dashboard'
    await router.replace(redirect)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '登录失败，请稍后重试'))
  }
}
</script>

<template>
  <main class="auth-page">
    <AuthShowcase />
    <section class="auth-form-pane">
      <div class="mobile-logo"><AppLogo light /></div>
      <div class="auth-box">
        <span class="hello">WELCOME BACK</span>
        <h2>继续你的学习旅程</h2>
        <p class="subtitle">登录后，AI 会接着昨天的进度陪你学习。</p>
        <el-alert v-if="auth.restoreError" class="session-alert" :title="auth.restoreError" type="warning" :closable="false" show-icon />
        <el-alert v-if="mockEnabled" class="demo-alert" title="演示模式已开启，当前使用虚拟账号" type="info" :closable="false" show-icon />
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="submit">
          <el-form-item label="邮箱" prop="email"><el-input v-model="form.email" size="large" :prefix-icon="Message" placeholder="name@university.edu" /></el-form-item>
          <el-form-item label="密码" prop="password"><el-input v-model="form.password" size="large" type="password" show-password :prefix-icon="Lock" placeholder="请输入密码" /></el-form-item>
          <div class="form-options"><span>登录信息仅保存在当前标签页</span><button type="button">忘记密码？</button></div>
          <el-button type="primary" size="large" class="submit" :loading="auth.loading" @click="submit">登录 StudyPilot</el-button>
        </el-form>
        <div class="divider"><span>还没有账号？</span></div>
        <el-button size="large" class="register-link" @click="router.push('/register')">创建学习账号</el-button>
        <p class="terms">登录即表示你同意《服务条款》和《隐私政策》</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page{min-height:100vh;display:grid;grid-template-columns:minmax(480px,1.12fr) minmax(430px,.88fr);background:#fff}.auth-form-pane{position:relative;display:flex;align-items:center;justify-content:center;padding:45px}.auth-box{width:min(100%,390px)}.mobile-logo{position:absolute;left:42px;top:36px}.hello{color:var(--brand);font-size:10px;font-weight:800;letter-spacing:2px}.auth-box h2{margin:12px 0 8px;color:#182342;font-size:29px;letter-spacing:-.8px}.subtitle{margin:0 0 25px;color:#818ba1;font-size:12px}.demo-alert,.session-alert{margin-bottom:22px;border-radius:10px}.demo-alert{background:#f1f3ff;border:1px solid #e0e4ff;color:#5b67b7}:deep(.el-form-item__label){color:#4b5670;font-size:11px;font-weight:650}:deep(.el-input__wrapper){padding:4px 12px}.form-options{display:flex;justify-content:space-between;align-items:center;margin:-2px 0 23px}.form-options span{color:#919aaf;font-size:10px}.form-options button{border:0;background:transparent;color:var(--brand);font-size:11px;cursor:pointer}.submit,.register-link{width:100%}.divider{display:flex;align-items:center;gap:13px;margin:25px 0 17px;color:#a0a8ba;font-size:10px}.divider::before,.divider::after{content:"";flex:1;height:1px;background:#e8ebf1}.register-link{color:#5361d9;border-color:#dfe3f3}.terms{text-align:center;margin:22px 0 0;color:#a0a8b8;font-size:9px}@media(min-width:951px){.mobile-logo{display:none}}@media(max-width:950px){.auth-page{display:block;background:linear-gradient(180deg,#f5f7ff,#fff 300px)}.auth-form-pane{min-height:100vh;padding:110px 24px 45px}.mobile-logo{left:24px;top:28px}}
</style>
