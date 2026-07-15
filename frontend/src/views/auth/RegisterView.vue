<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, Message, User } from '@element-plus/icons-vue'
import AppLogo from '@/components/AppLogo.vue'
import AuthShowcase from '@/components/AuthShowcase.vue'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage, mockEnabled } from '@/api/client'

const auth = useAuthStore()
const router = useRouter()
const formRef = ref<FormInstance>()
const form = reactive({ name: '', email: '', password: '', agree: true })
const rules: FormRules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }, { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 位', trigger: 'blur' }],
}
async function submit() {
  if (!await formRef.value?.validate().catch(() => false)) return
  if (!form.agree) return ElMessage.warning('请先阅读并同意服务条款和隐私政策')
  try {
    await auth.register(form.name, form.email, form.password)
    ElMessage.success('账号创建成功，已为你自动登录')
    await router.replace('/dashboard')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '注册失败，请稍后重试'))
  }
}
</script>

<template>
  <main class="auth-page">
    <AuthShowcase />
    <section class="auth-form-pane">
      <div class="mobile-logo"><AppLogo light /></div>
      <div class="auth-box">
        <span class="hello">START YOUR JOURNEY</span><h2>创建你的学习档案</h2>
        <p class="subtitle">只需一分钟，开始获得真正适合你的学习建议。</p>
        <el-alert v-if="mockEnabled" class="demo-alert" title="演示模式已开启，注册信息不会写入真实后端" type="info" :closable="false" show-icon />
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <el-form-item label="姓名 / 昵称" prop="name"><el-input v-model="form.name" size="large" :prefix-icon="User" placeholder="AI 将这样称呼你" /></el-form-item>
          <el-form-item label="邮箱" prop="email"><el-input v-model="form.email" size="large" :prefix-icon="Message" placeholder="name@university.edu" /></el-form-item>
          <el-form-item label="密码" prop="password"><el-input v-model="form.password" size="large" type="password" show-password :prefix-icon="Lock" placeholder="至少 8 位" /></el-form-item>
          <el-checkbox v-model="form.agree" class="agreement">我已阅读并同意《服务条款》和《隐私政策》</el-checkbox>
          <el-button type="primary" size="large" class="submit" :loading="auth.loading" @click="submit">创建账号</el-button>
        </el-form>
        <div class="divider"><span>已有账号？</span></div>
        <el-button size="large" class="login-link" @click="router.push('/login')">返回登录</el-button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth-page{min-height:100vh;display:grid;grid-template-columns:minmax(480px,1.12fr) minmax(430px,.88fr);background:#fff}.auth-form-pane{position:relative;display:flex;align-items:center;justify-content:center;padding:40px 45px}.auth-box{width:min(100%,390px)}.mobile-logo{position:absolute;left:42px;top:30px}.hello{color:var(--brand);font-size:10px;font-weight:800;letter-spacing:2px}.auth-box h2{margin:12px 0 8px;color:#182342;font-size:29px;letter-spacing:-.8px}.subtitle{margin:0 0 24px;color:#818ba1;font-size:12px}.demo-alert{margin-bottom:18px;border-radius:10px}:deep(.el-form-item){margin-bottom:17px}:deep(.el-form-item__label){color:#4b5670;font-size:11px;font-weight:650}:deep(.el-input__wrapper){padding:4px 12px}.agreement{margin:1px 0 20px;font-size:10px}.submit,.login-link{width:100%}.divider{display:flex;align-items:center;gap:13px;margin:22px 0 16px;color:#a0a8ba;font-size:10px}.divider::before,.divider::after{content:"";flex:1;height:1px;background:#e8ebf1}.login-link{color:#5361d9;border-color:#dfe3f3}@media(min-width:951px){.mobile-logo{display:none}}@media(max-width:950px){.auth-page{display:block;background:linear-gradient(180deg,#f5f7ff,#fff 300px)}.auth-form-pane{min-height:100vh;padding:100px 24px 35px}.mobile-logo{left:24px;top:25px}}
</style>
