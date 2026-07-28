<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getApiErrorMessage } from '@/api/client'
import { courseApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import type { NavigationItem } from '@/config/navigation'
import type { CourseListItem } from '@/types'

interface SearchResult {
  key: string
  kind: 'function' | 'course'
  title: string
  subtitle: string
  destination: string
}

const props = defineProps<{
  open: boolean
  entries: readonly NavigationItem[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'select-path': [path: string]
  closed: []
}>()

const auth = useAuthStore()
const inputRef = ref<HTMLInputElement>()
const resultListRef = ref<HTMLElement>()
const query = ref('')
const courses = ref<CourseListItem[]>([])
const coursesLoadedForUser = ref<number | null>(null)
const loadingCourses = ref(false)
const courseError = ref('')
const activeIndex = ref(0)
let requestVersion = 0

const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase())

function rankMatch(label: string, secondaryValues: string[]): number | null {
  const search = normalizedQuery.value
  if (!search) return 4

  const normalizedLabel = label.toLocaleLowerCase()
  if (normalizedLabel === search) return 0
  if (normalizedLabel.startsWith(search)) return 1
  if (normalizedLabel.includes(search)) return 2
  return secondaryValues.some((value) => value.toLocaleLowerCase().includes(search)) ? 3 : null
}

const functionResults = computed<SearchResult[]>(() => props.entries
  .map((entry, order) => ({ entry, order, rank: rankMatch(entry.label, entry.keywords) }))
  .filter((result): result is { entry: NavigationItem; order: number; rank: number } => result.rank !== null)
  .sort((left, right) => left.rank - right.rank || left.order - right.order)
  .map(({ entry }) => ({
    key: `function:${entry.path}`,
    kind: 'function' as const,
    title: entry.label,
    subtitle: entry.group,
    destination: entry.path,
  })))

const courseResults = computed<SearchResult[]>(() => courses.value
  .map((course) => ({
    course,
    rank: rankMatch(course.name, [course.code || '']),
  }))
  .filter((result): result is { course: CourseListItem; rank: number } => result.rank !== null)
  .sort((left, right) => (
    left.rank - right.rank
    || left.course.name.localeCompare(right.course.name, 'zh-CN')
    || left.course.id - right.course.id
  ))
  .map(({ course }) => ({
    key: `course:${course.id}`,
    kind: 'course' as const,
    title: course.name,
    subtitle: course.code ? `课程编号 · ${course.code}` : '我的课程',
    destination: `/courses/${course.id}`,
  })))

const results = computed(() => [...functionResults.value, ...courseResults.value])
const activeKey = computed(() => results.value[activeIndex.value]?.key || '')

function resetCourseCache() {
  requestVersion += 1
  courses.value = []
  coursesLoadedForUser.value = null
  courseError.value = ''
  loadingCourses.value = false
}

function resetSearchState() {
  resetCourseCache()
  query.value = ''
  activeIndex.value = 0
}

function scrollActiveResultIntoView() {
  void nextTick(() => {
    const active = resultListRef.value?.querySelector<HTMLElement>('[role="option"][aria-selected="true"]')
    active?.scrollIntoView({ block: 'nearest' })
  })
}

async function loadCourses(force = false) {
  const userId = auth.user?.id
  if (!userId) {
    resetCourseCache()
    return
  }
  if (!force && coursesLoadedForUser.value === userId) return

  const version = ++requestVersion
  loadingCourses.value = true
  courseError.value = ''
  try {
    const response = await courseApi.list()
    if (version !== requestVersion || auth.user?.id !== userId || !props.open) return
    courses.value = response.items.filter((course) => !course.archived)
    coursesLoadedForUser.value = userId
  } catch (error) {
    if (version !== requestVersion || auth.user?.id !== userId || !props.open) return
    courses.value = []
    coursesLoadedForUser.value = null
    courseError.value = getApiErrorMessage(error, '课程加载失败，请稍后重试')
  } finally {
    if (version === requestVersion) loadingCourses.value = false
  }
}

function focusInput() {
  void nextTick(() => inputRef.value?.focus())
}

function close() {
  emit('update:open', false)
}

function choose(result: SearchResult | undefined) {
  if (!result) return
  emit('update:open', false)
  emit('select-path', result.destination)
}

function moveHighlight(offset: number) {
  if (!results.value.length) return
  activeIndex.value = (activeIndex.value + offset + results.value.length) % results.value.length
}

function chooseHighlighted() {
  choose(results.value[activeIndex.value])
}

watch(() => auth.user?.id, resetSearchState)
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    resetSearchState()
    focusInput()
    void loadCourses(true)
  } else {
    resetSearchState()
  }
})
watch(results, (currentResults) => {
  if (activeIndex.value >= currentResults.length) activeIndex.value = 0
})
watch(activeKey, scrollActiveResultIntoView)

function handleSessionExpired() {
  resetSearchState()
}

onMounted(() => window.addEventListener('studypilot:session-expired', handleSessionExpired))
onBeforeUnmount(() => window.removeEventListener('studypilot:session-expired', handleSessionExpired))

defineExpose({ focusInput })
</script>

<template>
  <el-dialog
    :model-value="open"
    width="min(680px, calc(100vw - 28px))"
    :show-close="false"
    class="quick-search-dialog"
    @update:model-value="emit('update:open', $event)"
    @closed="emit('closed')"
  >
    <div class="quick-search">
      <div class="search-input-wrap">
        <el-icon><Search /></el-icon>
        <input
          ref="inputRef"
          v-model="query"
          aria-label="搜索功能或课程"
          autocomplete="off"
          placeholder="搜索功能或课程……"
          @keydown.down.prevent="moveHighlight(1)"
          @keydown.up.prevent="moveHighlight(-1)"
          @keydown.enter.prevent="chooseHighlighted"
          @keydown.esc.prevent="close"
        >
        <kbd>Esc</kbd>
      </div>

      <div ref="resultListRef" class="result-list" role="listbox" aria-label="搜索结果">
        <section v-if="functionResults.length" class="result-group">
          <h3>功能入口</h3>
          <button
            v-for="result in functionResults"
            :key="result.key"
            class="result-item"
            :class="{ 'is-active': activeKey === result.key }"
            role="option"
            :aria-selected="activeKey === result.key"
            @mouseenter="activeIndex = results.findIndex((item) => item.key === result.key)"
            @click="choose(result)"
          >
            <span>{{ result.title }}</span><small>{{ result.subtitle }}</small>
          </button>
        </section>

        <section class="result-group course-group">
          <div class="group-heading">
            <h3>我的课程</h3>
            <button v-if="coursesLoadedForUser !== null && !loadingCourses" class="refresh-button" @click="loadCourses(true)">刷新课程</button>
          </div>
          <p v-if="loadingCourses" class="result-message" aria-live="polite">正在加载真实课程…</p>
          <div v-else-if="courseError" class="result-error" role="alert">
            <span>{{ courseError }}</span>
            <button class="retry-button" @click="loadCourses(true)">重新加载课程</button>
          </div>
          <template v-else-if="courseResults.length">
            <button
              v-for="result in courseResults"
              :key="result.key"
              class="result-item"
              :class="{ 'is-active': activeKey === result.key }"
              role="option"
              :aria-selected="activeKey === result.key"
              @mouseenter="activeIndex = results.findIndex((item) => item.key === result.key)"
              @click="choose(result)"
            >
              <span>{{ result.title }}</span><small>{{ result.subtitle }}</small>
            </button>
          </template>
          <p v-else-if="!normalizedQuery" class="result-message">暂无可搜索的课程</p>
        </section>

        <p v-if="!results.length && !loadingCourses && !courseError" class="empty-state">没有匹配的功能或课程</p>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.quick-search{display:flex;flex-direction:column;gap:16px}.search-input-wrap{height:46px;display:flex;align-items:center;gap:10px;padding:0 13px;border:1px solid #ccd7ef;border-radius:12px;background:#fff;color:#687595;box-shadow:0 0 0 3px rgba(93,110,250,.08)}.search-input-wrap input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:#283553;font:inherit;font-size:14px}.search-input-wrap kbd{padding:3px 6px;border:1px solid #e0e5ef;border-radius:5px;background:#f6f8fb;color:#7e8aa1;font:10px inherit}.result-list{max-height:min(58vh,510px);overflow:auto;padding-right:3px}.result-group+.result-group{margin-top:18px}.result-group h3{margin:0 0 7px;color:#7d89a1;font-size:11px;font-weight:800;letter-spacing:.8px}.group-heading{display:flex;align-items:center;justify-content:space-between}.group-heading h3{margin-bottom:7px}.result-item{width:100%;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 11px;border:0;border-radius:9px;background:transparent;color:#33415f;text-align:left;cursor:pointer}.result-item:hover,.result-item.is-active{background:#eef1ff;color:#4458d9}.result-item span{font-size:13px;font-weight:700}.result-item small{color:#8792aa;font-size:11px}.result-message,.empty-state{margin:4px 0;padding:10px 11px;color:#7e8aa1;font-size:12px}.result-error{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 11px;border-radius:9px;background:#fff4f4;color:#a84b4b;font-size:12px}.refresh-button,.retry-button{border:0;background:transparent;color:#5368db;font:inherit;font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}.retry-button{padding:0}
</style>
