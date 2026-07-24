<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Fold, Menu as MenuIcon, Search, UserFilled } from '@element-plus/icons-vue'
import { mockEnabled } from '@/api/client'
import { courseApi } from '@/api/services'
import { navigationGroups, navigationItems } from '@/config/navigation'
import AppLogo from '@/components/AppLogo.vue'
import GlobalQuickSearch from '@/components/GlobalQuickSearch.vue'
import { useAuthStore } from '@/stores/auth'
import type { CourseListItem } from '@/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = ref(false)
const mobile = ref(false)
const drawerOpen = ref(false)
const searchOpen = ref(false)
const quickSearchRef = ref<InstanceType<typeof GlobalQuickSearch>>()
const desktopSearchTrigger = ref<HTMLButtonElement>()
const mobileSearchTrigger = ref<HTMLButtonElement>()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | null>(null)
const coursesLoading = ref(false)
let lastSearchTrigger: 'desktop' | 'mobile' = 'desktop'

const activeMenu = computed(() => String(route.meta.activeMenu || route.path))
const courseAwarePaths = new Set(['/today', '/plan', '/chat', '/practice', '/recommendations', '/statistics', '/mastery', '/upload'])

function parseCourseId(value: unknown) {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

async function loadCourses() {
  coursesLoading.value = true
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
    const fromRoute = parseCourseId(route.query.courseId)
    const stored = parseCourseId(window.localStorage.getItem('study-pilot-course-id'))
    const preferred = fromRoute ?? stored
    selectedCourseId.value = courses.value.some((course) => course.id === preferred) ? preferred : (courses.value[0]?.id ?? null)
    if (selectedCourseId.value) window.localStorage.setItem('study-pilot-course-id', String(selectedCourseId.value))
  } catch {
    courses.value = []
    selectedCourseId.value = null
  } finally {
    coursesLoading.value = false
  }
}

async function changeCourse(value: number) {
  selectedCourseId.value = value
  window.localStorage.setItem('study-pilot-course-id', String(value))
  if (courseAwarePaths.has(route.path)) {
    await router.replace({ path: route.path, query: { ...route.query, courseId: String(value) } })
  }
}

function syncViewport() {
  mobile.value = window.innerWidth < 900
  if (window.innerWidth < 1180 && !mobile.value) collapsed.value = true
}

async function logout() {
  searchOpen.value = false
  auth.logout()
  await router.replace('/login')
}

function go(path: string) {
  drawerOpen.value = false
  void router.push(path)
}

function openSearch(source: 'desktop' | 'mobile') {
  lastSearchTrigger = source
  if (searchOpen.value) {
    quickSearchRef.value?.focusInput()
    return
  }
  searchOpen.value = true
}

function closeSearch() {
  searchOpen.value = false
}

function restoreSearchFocus() {
  void nextTick(() => {
    const trigger = lastSearchTrigger === 'mobile' ? mobileSearchTrigger.value : desktopSearchTrigger.value
    trigger?.focus()
  })
}

function handleSearchSelection(path: string) {
  closeSearch()
  void router.push(path)
}

function isEditableTarget(target: EventTarget | null) {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || (target instanceof HTMLElement && target.isContentEditable)
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key.toLocaleLowerCase() !== 'k' || (!event.ctrlKey && !event.metaKey)) return
  if (!searchOpen.value && isEditableTarget(event.target)) return
  event.preventDefault()
  openSearch(mobile.value ? 'mobile' : 'desktop')
}

onMounted(() => {
  syncViewport()
  void loadCourses()
  window.addEventListener('resize', syncViewport)
  window.addEventListener('keydown', handleGlobalKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewport)
  window.removeEventListener('keydown', handleGlobalKeydown)
})
watch(() => route.query.courseId, (value) => {
  const id = parseCourseId(value)
  if (id && courses.value.some((course) => course.id === id)) {
    selectedCourseId.value = id
    window.localStorage.setItem('study-pilot-course-id', String(id))
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside v-if="!mobile" class="sidebar">
      <div class="sidebar-logo"><AppLogo :collapsed="collapsed" /></div>
      <el-scrollbar class="sidebar-scroll">
        <el-menu :default-active="activeMenu" router :collapse="collapsed" :collapse-transition="false" class="sidebar-menu">
          <template v-for="group in navigationGroups" :key="group.label">
            <div v-if="!collapsed" class="nav-group-label">{{ group.label }}</div>
            <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title><span>{{ item.label }}</span></template>
            </el-menu-item>
          </template>
        </el-menu>
      </el-scrollbar>
      <div class="sidebar-bottom">
        <button class="collapse-btn" @click="collapsed = !collapsed"><el-icon><Fold /></el-icon><span v-if="!collapsed">收起导航</span></button>
      </div>
    </aside>

    <el-drawer v-model="drawerOpen" direction="ltr" size="270px" :with-header="false" class="mobile-drawer">
      <div class="drawer-logo"><AppLogo /></div>
      <el-menu :default-active="activeMenu" class="drawer-menu">
        <template v-for="group in navigationGroups" :key="group.label">
          <div class="nav-group-label">{{ group.label }}</div>
          <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path" @click="go(item.path)">
            <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-drawer>

    <section class="content-shell">
      <header class="topbar">
        <button v-if="mobile" class="icon-button" aria-label="打开导航" @click="drawerOpen = true"><el-icon><MenuIcon /></el-icon></button>
        <div v-if="!mobile" class="course-context">
          <span>当前课程</span>
          <el-select
            :model-value="selectedCourseId"
            :loading="coursesLoading"
            placeholder="先创建一门课程"
            @change="changeCourse"
          >
            <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.name" />
          </el-select>
        </div>
        <button
          v-if="!mobile"
          ref="desktopSearchTrigger"
          class="global-search"
          aria-label="打开全局快捷搜索"
          @click="openSearch('desktop')"
        >
          <el-icon><Search /></el-icon><span>搜索功能或课程……</span><kbd>Ctrl K</kbd>
        </button>
        <button
          v-if="mobile"
          ref="mobileSearchTrigger"
          class="icon-button"
          aria-label="打开全局快捷搜索"
          @click="openSearch('mobile')"
        ><el-icon><Search /></el-icon></button>
        <div class="top-actions">
          <span v-if="mockEnabled" class="demo-state"><i></i><span>演示模式</span></span>
          <el-dropdown trigger="click">
            <div class="user-chip">
              <el-avatar :size="34" class="user-avatar"><UserFilled /></el-avatar>
              <div v-if="!mobile"><strong>{{ auth.user?.displayName || '学习者' }}</strong><small>{{ auth.user?.email }}</small></div>
            </div>
            <template #dropdown><el-dropdown-menu><el-dropdown-item @click="router.push('/settings')">个人设置</el-dropdown-item><el-dropdown-item divided @click="logout">退出登录</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </div>
      </header>
      <main class="page-content"><RouterView v-slot="{ Component }"><Transition name="page" mode="out-in"><component :is="Component" /></Transition></RouterView></main>
    </section>

    <GlobalQuickSearch
      ref="quickSearchRef"
      v-model:open="searchOpen"
      :entries="navigationItems"
      @select-path="handleSearchSelection"
      @closed="restoreSearchFocus"
    />
  </div>
</template>

<style scoped>
.app-shell{min-height:100vh;background:var(--canvas)}.sidebar{position:fixed;inset:0 auto 0 0;width:236px;display:flex;flex-direction:column;overflow:hidden;background:linear-gradient(185deg,#0d1428 0%,#131c36 56%,#0a1123 100%);z-index:30;transition:width .2s ease;box-shadow:12px 0 40px rgba(8,16,37,.1)}.sidebar::before{content:"";position:absolute;width:210px;height:210px;left:-120px;top:-80px;border-radius:50%;background:#6255f5;filter:blur(1px);opacity:.15}.is-collapsed .sidebar{width:76px}.sidebar-logo{position:relative;height:84px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid rgba(255,255,255,.06)}.is-collapsed .sidebar-logo{padding:0 18px}.sidebar-scroll{flex:1}.sidebar-menu{border:0!important;background:transparent;padding:13px 11px 16px}.nav-group-label{padding:19px 12px 8px;color:#5e6b8b;font-size:9px;font-weight:850;letter-spacing:1.7px;text-transform:uppercase}.sidebar-menu :deep(.el-menu-item){position:relative;height:43px;line-height:43px;margin:3px 0;border-radius:11px;color:#9aa7c4;padding-left:13px!important;gap:6px;font-size:13px}.sidebar-menu :deep(.el-menu-item .el-icon){font-size:18px}.sidebar-menu :deep(.el-menu-item:hover){color:#fff;background:rgba(255,255,255,.055)}.sidebar-menu :deep(.el-menu-item.is-active){color:#fff;background:linear-gradient(100deg,rgba(103,88,245,.94),rgba(91,78,225,.72));box-shadow:0 9px 24px rgba(50,42,142,.3)}.sidebar-menu :deep(.el-menu-item.is-active)::after{content:"";position:absolute;right:8px;width:4px;height:4px;border-radius:50%;background:#7cebd7;box-shadow:0 0 0 4px rgba(124,235,215,.12)}.sidebar-menu :deep(.el-menu--collapse .el-menu-item){padding:0 15px!important;justify-content:center}.sidebar-menu :deep(.el-menu--collapse .el-menu-item.is-active)::after{display:none}.sidebar-bottom{position:relative;padding:11px;border-top:1px solid rgba(255,255,255,.06)}.collapse-btn{width:100%;height:40px;display:flex;align-items:center;justify-content:center;gap:9px;color:#7886a7;background:rgba(255,255,255,.025);border:0;border-radius:10px;cursor:pointer;font-size:11px}.collapse-btn:hover{background:rgba(255,255,255,.06);color:white}.content-shell{min-height:100vh;margin-left:236px;transition:margin-left .2s ease}.is-collapsed .content-shell{margin-left:76px}.topbar{position:sticky;top:0;z-index:20;height:72px;display:flex;align-items:center;gap:16px;padding:0 38px;background:rgba(242,244,248,.86);backdrop-filter:blur(20px);border-bottom:1px solid rgba(217,222,232,.82)}.course-context{min-width:230px;display:flex;align-items:center;gap:10px}.course-context>span{flex:none;color:#758096;font-size:11px;font-weight:750}.course-context :deep(.el-select){width:170px}.course-context :deep(.el-select__wrapper){min-height:42px;border-radius:10px;box-shadow:0 0 0 1px #dfe4ed inset;background:#fff}.global-search{width:min(360px,30vw);height:42px;display:flex;align-items:center;gap:10px;padding:0 14px;border:1px solid #dfe4ed;border-radius:10px;background:rgba(255,255,255,.88);color:#909aaf;cursor:pointer;text-align:left;transition:border-color .15s ease,box-shadow .15s ease,background .15s ease}.global-search:hover{border-color:#cfd4e4;background:#fff;box-shadow:0 8px 24px rgba(33,43,73,.07)}.global-search span{flex:1;min-width:0;font:12px inherit}.global-search kbd{padding:4px 7px;border:1px solid #e0e4ec;border-radius:6px;background:#f5f6f9;color:#818ba1;font:10px inherit;white-space:nowrap}.top-actions{margin-left:auto;display:flex;align-items:center;gap:13px}.demo-state{display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid #d9e8e4;border-radius:999px;background:#f2fbf8;color:#378676;font-size:10px;font-weight:750}.demo-state i{width:7px;height:7px;border-radius:50%;background:#18b493;box-shadow:0 0 0 3px #d7f3eb}.icon-button{position:relative;width:40px;height:40px;display:grid;place-items:center;border:1px solid #e0e4ec;border-radius:8px;background:#fff;color:#63708d;cursor:pointer;font-size:16px}.user-chip{display:flex;align-items:center;gap:11px;padding-left:2px;cursor:pointer}.user-avatar{background:linear-gradient(145deg,#7163f6,#9a5ee8);color:white;box-shadow:0 7px 18px rgba(91,74,218,.18)}.user-chip div{display:flex;flex-direction:column;line-height:1.15}.user-chip strong{font-size:12px;color:#303a52}.user-chip small{max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:4px;font-size:10px;color:#8b95aa}.page-content{max-width:1520px;margin:0 auto;padding:34px 40px 60px}.drawer-logo{padding:21px;background:#0e162b}.drawer-menu{border:0}.page-enter-active,.page-leave-active{transition:opacity .15s ease,transform .15s ease}.page-enter-from{opacity:0;transform:translateY(5px)}.page-leave-to{opacity:0;transform:translateY(-3px)}@media(max-width:1100px){.course-context{min-width:190px}.course-context>span{display:none}.course-context :deep(.el-select){width:190px}.global-search{width:42px;padding:0;justify-content:center}.global-search span,.global-search kbd{display:none}}@media(max-width:899px){.content-shell{margin-left:0}.topbar{height:62px;padding:0 16px}.page-content{padding:24px 16px 40px}.demo-state span{display:none}.demo-state{padding:7px}.top-actions{gap:7px}}
</style>
