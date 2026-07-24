<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Connection, Lock, Setting, User } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage } from '@/api/client'
import { profileApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import type { BackendUser, UserPreferences } from '@/types'

const route = useRoute()
const auth = useAuthStore()
const tab = ref('profile')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const user = ref<BackendUser | null>(null)
const profileDraft = reactive({ display_name: '', timezone: 'Asia/Shanghai' })
const preferenceDraft = reactive<UserPreferences>({ foundation_level: 'basic', learning_order: 'explain_first', preferred_difficulty: 'adaptive', preferred_resource_types: [], session_minutes: 45, daily_minutes: 120, needs_exam_focus: true, needs_error_points: true, needs_derivation: false })
let savedProfile = ''
let savedPreferences = ''

const timezones = ['Asia/Shanghai', 'Asia/Tokyo', 'America/New_York', 'America/Los_Angeles', 'Europe/London', 'UTC']
const avatarInitial = computed(() => profileDraft.display_name.trim().slice(0, 1) || '学')
const profileDirty = computed(() => JSON.stringify(profileDraft) !== savedProfile)
const preferencesDirty = computed(() => JSON.stringify(preferenceDraft) !== savedPreferences)
const createdAt = computed(() => user.value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(user.value.created_at)) : '')

function applyProfile(data: { user: BackendUser; preferences: UserPreferences }) {
  user.value = data.user
  profileDraft.display_name = data.user.display_name
  profileDraft.timezone = data.user.timezone
  Object.assign(preferenceDraft, data.preferences)
  savedProfile = JSON.stringify(profileDraft)
  savedPreferences = JSON.stringify(preferenceDraft)
}

async function load() {
  loading.value = true
  error.value = ''
  try { applyProfile(await profileApi.get()) } catch (cause) { error.value = getApiErrorMessage(cause, '个人资料加载失败') } finally { loading.value = false }
}

function resetCurrent() {
  if (tab.value === 'profile') {
    const saved = JSON.parse(savedProfile || '{}')
    Object.assign(profileDraft, saved)
  } else if (tab.value === 'learning') {
    const saved = JSON.parse(savedPreferences || '{}')
    Object.assign(preferenceDraft, saved)
  }
}

async function saveProfile() {
  if (saving.value || !profileDirty.value) return
  saving.value = true
  try {
    const updated = await profileApi.updateUser({ ...profileDraft })
    profileDraft.display_name = updated.display_name
    profileDraft.timezone = updated.timezone
    user.value = updated
    savedProfile = JSON.stringify(profileDraft)
    auth.updateCurrentUser(updated)
    ElMessage.success('个人资料已保存')
  } catch (cause) { ElMessage.error(getApiErrorMessage(cause, '个人资料保存失败')) } finally { saving.value = false }
}

async function savePreferences() {
  if (saving.value || !preferencesDirty.value) return
  if (preferenceDraft.session_minutes > preferenceDraft.daily_minutes) return ElMessage.warning('单次学习时长不能超过每日预算')
  saving.value = true
  try {
    const updated = await profileApi.updatePreferences({ ...preferenceDraft })
    Object.assign(preferenceDraft, updated)
    savedPreferences = JSON.stringify(preferenceDraft)
    ElMessage.success('学习偏好已保存')
  } catch (cause) { ElMessage.error(getApiErrorMessage(cause, '学习偏好保存失败')) } finally { saving.value = false }
}

watch(() => route.query.tab, (value) => { if (value === 'learning') tab.value = 'learning' }, { immediate: true })
onMounted(() => { void load() })
</script>

<template>
  <div>
    <PageHeader title="个人设置" eyebrow="账户与偏好" description="管理真实账户资料和用于生成学习计划的偏好。" />
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="load">重试</el-button></template></el-alert>
    <div v-else v-loading="loading" class="settings-layout">
      <aside class="content-card settings-nav">
        <button :class="{ active: tab === 'profile' }" @click="tab = 'profile'"><el-icon><User /></el-icon><span><b>个人资料</b><small>昵称、邮箱与时区</small></span></button>
        <button :class="{ active: tab === 'learning' }" @click="tab = 'learning'"><el-icon><Setting /></el-icon><span><b>学习偏好</b><small>计划默认约束</small></span></button>
        <button :class="{ active: tab === 'models' }" @click="tab = 'models'"><el-icon><Connection /></el-icon><span><b>模型与服务</b><small>后续开放</small></span></button>
        <button :class="{ active: tab === 'notifications' }" @click="tab = 'notifications'"><el-icon><Bell /></el-icon><span><b>通知设置</b><small>后续开放</small></span></button>
        <button :class="{ active: tab === 'security' }" @click="tab = 'security'"><el-icon><Lock /></el-icon><span><b>账户与安全</b><small>当前登录信息</small></span></button>
      </aside>
      <main class="content-card card-pad settings-content">
        <template v-if="tab === 'profile' && user">
          <div class="section-title"><div><h2>个人资料</h2><p>仅保存当前账号的昵称和时区。</p></div><el-avatar :size="64" class="avatar">{{ avatarInitial }}</el-avatar></div>
          <el-form label-position="top" class="form-grid"><el-form-item label="昵称"><el-input v-model="profileDraft.display_name" maxlength="100" /></el-form-item><el-form-item label="邮箱"><el-input :model-value="user.email" disabled /></el-form-item><el-form-item label="时区"><el-select v-model="profileDraft.timezone" style="width:100%"><el-option v-for="zone in timezones" :key="zone" :label="zone" :value="zone" /></el-select></el-form-item><el-form-item label="注册时间"><el-input :model-value="createdAt" disabled /></el-form-item></el-form>
          <div class="actions"><el-button :disabled="saving || !profileDirty" @click="resetCurrent">恢复已保存值</el-button><el-button type="primary" :loading="saving" :disabled="saving || !profileDirty" @click="saveProfile">保存个人资料</el-button></div>
        </template>
        <template v-else-if="tab === 'learning'">
          <div class="section-title"><div><h2>学习偏好</h2><p>只影响之后主动生成的候选计划，不会改写既有计划。</p></div></div>
          <div class="setting-groups"><section><h3>学习方式</h3><div class="setting-row"><div><b>基础水平</b><p>影响初始任务的讲解、重点学习或综合应用方式。</p></div><el-select v-model="preferenceDraft.foundation_level"><el-option label="基础讲解" value="basic" /><el-option label="重点学习" value="intermediate" /><el-option label="综合应用" value="advanced" /></el-select></div><div class="setting-row"><div><b>内容安排顺序</b><p>始终遵守前置关系；薄弱优先仅使用真实学习记录。</p></div><el-select v-model="preferenceDraft.learning_order"><el-option label="先讲解再练习" value="explain_first" /><el-option label="优先真实薄弱点" value="weakness_first" /></el-select></div><div class="setting-row"><div><b>偏好难度</b><p>控制普通任务的难度调整。</p></div><el-select v-model="preferenceDraft.preferred_difficulty"><el-option label="基础" value="basic" /><el-option label="自适应" value="adaptive" /><el-option label="进阶" value="advanced" /></el-select></div></section><section><h3>时间与资料</h3><div class="setting-row"><div><b>单次学习时长</b><p>普通学习任务不会超过此时长。</p></div><el-input-number v-model="preferenceDraft.session_minutes" :min="15" :max="180" /><span>分钟</span></div><div class="setting-row"><div><b>每日学习预算</b><p>排期每天不会超过此预算。</p></div><el-input-number v-model="preferenceDraft.daily_minutes" :min="15" :max="720" /><span>分钟</span></div><div class="resource-row"><b>偏好资料类型</b><p>本轮仅保存并记录到计划快照，尚不为任务伪造资料绑定。</p><el-checkbox-group v-model="preferenceDraft.preferred_resource_types"><el-checkbox label="pdf">PDF</el-checkbox><el-checkbox label="ppt">PPT</el-checkbox><el-checkbox label="markdown">Markdown</el-checkbox><el-checkbox label="text">文本</el-checkbox></el-checkbox-group></div></section><section><h3>计划策略</h3><div class="setting-row"><div><b>考试冲刺任务</b><p>容量允许时加入阶段测试与综合复习。</p></div><el-switch v-model="preferenceDraft.needs_exam_focus" /></div><div class="setting-row"><div><b>优先真实薄弱知识点</b><p>只对 attempts &gt; 0 的真实掌握度记录生效；没有学习记录不会被当作薄弱点。</p></div><el-switch v-model="preferenceDraft.needs_error_points" /></div><div class="setting-row"><div><b>增加推导类任务</b><p>使用规则化“概念推导”任务标题，不调用外部模型。</p></div><el-switch v-model="preferenceDraft.needs_derivation" /></div></section></div>
          <div class="actions"><el-button :disabled="saving || !preferencesDirty" @click="resetCurrent">恢复已保存值</el-button><el-button type="primary" :loading="saving" :disabled="saving || !preferencesDirty" @click="savePreferences">保存学习偏好</el-button></div>
        </template>
        <template v-else-if="tab === 'models'"><h2>模型与服务</h2><p class="honest">模型 Provider 由后端环境变量配置。本页面不读取、不保存和不展示任何 API Key；外部模型尚未在本轮接入。</p><el-button disabled>配置（后续开放）</el-button><el-button disabled>工具权限（后续开放）</el-button></template>
        <template v-else-if="tab === 'notifications'"><h2>通知设置</h2><p class="honest">站内通知和邮件通知尚未实现。</p></template>
        <template v-else><h2>账户与安全</h2><p class="honest">当前邮箱：{{ user?.email }}。当前登录 Token 仅保存在浏览器 sessionStorage。</p><el-button disabled>修改密码（暂未开放）</el-button><el-button disabled>管理会话（暂未开放）</el-button><el-button disabled>导出或删除数据（暂未开放）</el-button></template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:16px}.settings-layout{display:grid;grid-template-columns:235px minmax(0,1fr);gap:17px}.settings-nav{height:max-content;padding:9px}.settings-nav button{width:100%;display:flex;align-items:center;gap:10px;padding:12px;border:0;border-radius:10px;background:transparent;color:#7d879b;text-align:left;cursor:pointer}.settings-nav button.active{background:#eef0ff;color:#5968df}.settings-nav span{display:flex;flex-direction:column}.settings-nav b{font-size:9px}.settings-nav small,.section-title p,.setting-row p,.resource-row p,.honest{color:#929bad;font-size:8px}.settings-content{min-height:500px}.section-title{display:flex;justify-content:space-between;align-items:center;padding-bottom:17px;margin-bottom:18px;border-bottom:1px solid #edf0f4}.section-title h2,h2{margin:0;color:#3c4762;font-size:15px}.section-title p{margin:6px 0 0}.avatar{background:linear-gradient(145deg,#6171ed,#9b6be2)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 16px}.setting-groups{display:grid;gap:18px}.setting-groups section{border:1px solid #e5e9f0;border-radius:12px;overflow:hidden}.setting-groups h3{padding:11px 14px;margin:0;background:#f8f9fc;color:#68738a;font-size:9px}.setting-row{display:flex;align-items:center;gap:10px;padding:13px 15px;border-top:1px solid #edf0f4}.setting-row>div{display:flex;flex:1;flex-direction:column}.setting-row b,.resource-row b{font-size:9px;color:#48536c}.setting-row p{margin:5px 0 0}.setting-row>span{color:#8e97aa;font-size:8px}.resource-row{padding:13px 15px;border-top:1px solid #edf0f4}.resource-row p{margin:5px 0 10px}.actions{display:flex;justify-content:flex-end;gap:9px;margin-top:18px}.honest{margin:12px 0 18px;line-height:1.7}@media(max-width:800px){.settings-layout{grid-template-columns:1fr}.settings-nav{display:flex;overflow:auto}.settings-nav button{min-width:145px}.form-grid{grid-template-columns:1fr}}
</style>
