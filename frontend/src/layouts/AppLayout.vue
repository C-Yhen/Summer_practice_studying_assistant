<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Fold, Menu as MenuIcon, Search, UserFilled } from '@element-plus/icons-vue'
import { mockEnabled } from '@/api/client'
import { navigationGroups, navigationItems } from '@/config/navigation'
import AppLogo from '@/components/AppLogo.vue'
import GlobalQuickSearch from '@/components/GlobalQuickSearch.vue'
import { useAuthStore } from '@/stores/auth'

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
let lastSearchTrigger: 'desktop' | 'mobile' = 'desktop'

const activeMenu = computed(() => String(route.meta.activeMenu || route.path))

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
  window.addEventListener('resize', syncViewport)
  window.addEventListener('keydown', handleGlobalKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', syncViewport)
  window.removeEventListener('keydown', handleGlobalKeydown)
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
        <button
          v-else
          ref="desktopSearchTrigger"
          class="global-search"
          aria-label="打开全局快捷搜索"
          @click="openSearch('desktop')"
        >
          <el-icon><Search /></el-icon><span>搜索功能或课程……</span><kbd>Ctrl/⌘ K</kbd>
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
.app-shell{min-height:100vh;background:var(--canvas)}.sidebar{position:fixed;inset:0 auto 0 0;width:238px;display:flex;flex-direction:column;background:linear-gradient(180deg,#0c1838 0%,#101c3d 58%,#0c1632 100%);z-index:30;transition:width .2s ease;box-shadow:10px 0 35px rgba(10,24,58,.06)}.is-collapsed .sidebar{width:76px}.sidebar-logo{height:78px;display:flex;align-items:center;padding:0 20px;border-bottom:1px solid rgba(255,255,255,.06)}.is-collapsed .sidebar-logo{padding:0 19px}.sidebar-scroll{flex:1}.sidebar-menu{border:0!important;background:transparent;padding:14px 10px}.nav-group-label{padding:17px 13px 8px;color:#627096;font-size:9px;font-weight:800;letter-spacing:1.6px}.sidebar-menu :deep(.el-menu-item){height:42px;line-height:42px;margin:3px 0;border-radius:10px;color:#aab5d4;padding-left:13px!important;gap:2px}.sidebar-menu :deep(.el-menu-item .el-icon){font-size:17px}.sidebar-menu :deep(.el-menu-item:hover){color:#fff;background:rgba(255,255,255,.055)}.sidebar-menu :deep(.el-menu-item.is-active){color:#fff;background:linear-gradient(100deg,rgba(93,110,250,.92),rgba(94,104,226,.72));box-shadow:0 8px 20px rgba(66,78,188,.24)}.sidebar-menu :deep(.el-menu--collapse .el-menu-item){padding:0 16px!important;justify-content:center}.sidebar-bottom{padding:12px;border-top:1px solid rgba(255,255,255,.06)}.collapse-btn{width:100%;height:38px;display:flex;align-items:center;justify-content:center;gap:9px;color:#7e8bb0;background:transparent;border:0;border-radius:10px;cursor:pointer}.collapse-btn:hover{background:rgba(255,255,255,.05);color:white}.content-shell{min-height:100vh;margin-left:238px;transition:margin-left .2s ease}.is-collapsed .content-shell{margin-left:76px}.topbar{position:sticky;top:0;z-index:20;height:66px;display:flex;align-items:center;gap:16px;padding:0 30px;background:rgba(248,250,254,.88);backdrop-filter:blur(16px);border-bottom:1px solid rgba(218,224,237,.82)}.global-search{width:min(420px,42vw);height:38px;display:flex;align-items:center;gap:9px;padding:0 12px;border:1px solid #dde3ef;border-radius:11px;background:#fff;color:#9aa4bb;cursor:pointer;text-align:left}.global-search span{flex:1;min-width:0;font:12px inherit}.global-search kbd{padding:3px 6px;border:1px solid #e0e5ef;border-radius:5px;background:#f6f8fb;color:#929cb2;font:10px inherit;white-space:nowrap}.top-actions{margin-left:auto;display:flex;align-items:center;gap:11px}.demo-state{display:flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid #dce5e2;border-radius:999px;background:#f5fbf9;color:#428477;font-size:10px;font-weight:700}.demo-state i{width:7px;height:7px;border-radius:50%;background:#18aa88;box-shadow:0 0 0 3px #d9f3ec}.icon-button{position:relative;width:36px;height:36px;display:grid;place-items:center;border:1px solid #e0e5ef;border-radius:10px;background:#fff;color:#63708d;cursor:pointer;font-size:16px}.user-chip{display:flex;align-items:center;gap:9px;padding-left:2px;cursor:pointer}.user-avatar{background:linear-gradient(145deg,#6171f3,#9b68ec);color:white}.user-chip div{display:flex;flex-direction:column;line-height:1.15}.user-chip strong{font-size:11px;color:#303b59}.user-chip small{margin-top:4px;font-size:9px;color:#8f99ae}.page-content{max-width:1600px;margin:0 auto;padding:26px 30px 46px}.drawer-logo{padding:20px;background:#0c1838}.drawer-menu{border:0}.page-enter-active,.page-leave-active{transition:opacity .15s ease,transform .15s ease}.page-enter-from{opacity:0;transform:translateY(5px)}.page-leave-to{opacity:0;transform:translateY(-3px)}@media(max-width:899px){.content-shell{margin-left:0}.topbar{height:60px;padding:0 16px}.page-content{padding:20px 16px 38px}.demo-state span{display:none}.demo-state{padding:7px}.top-actions{gap:7px}}
</style>
