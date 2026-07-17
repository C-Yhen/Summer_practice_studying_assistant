<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import { useRoute, useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import EChart from '@/components/EChart.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi, learningApi } from '@/api/services'
import type { CourseListItem, KnowledgeMasteryItem } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | null>(null)
const coursesLoading = ref(false)
const coursesError = ref('')
const items = ref<KnowledgeMasteryItem[]>([])
const loading = ref(false)
const loadError = ref('')
let loadVersion = 0
let internalRouteUpdate = false

const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value) || null)
const recorded = computed(() => items.value.filter((item) => item.has_record && item.score !== null))
const sorted = computed(() => [...items.value].sort((left, right) => {
  if (!left.has_record && right.has_record) return 1
  if (left.has_record && !right.has_record) return -1
  return (left.score ?? 1) - (right.score ?? 1)
}))
const average = computed(() => recorded.value.length
  ? Math.round(recorded.value.reduce((sum, item) => sum + (item.score || 0), 0) / recorded.value.length * 100)
  : null)
const chartOption = computed<EChartsOption>(() => ({
  grid: { top: 16, right: 18, bottom: 10, left: 12, containLabel: true },
  xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
  yAxis: { type: 'category', data: recorded.value.map((item) => item.knowledge_point), axisLabel: { width: 120, overflow: 'truncate' } },
  series: [{ type: 'bar', data: recorded.value.map((item) => Math.round((item.score || 0) * 100)), itemStyle: { color: '#6372e8', borderRadius: [0, 5, 5, 0] } }],
}))

function queryCourse(): { present: boolean; id: number | null } {
  const rawValue = route.query.courseId
  if (rawValue === undefined) return { present: false, id: null }
  const raw = Array.isArray(rawValue) ? rawValue[0] : rawValue
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return { present: true, id: Number.isInteger(parsed) && parsed > 0 ? parsed : null }
}

function pageError(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
  } catch (error) {
    courses.value = []
    coursesError.value = pageError(error, '课程列表加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function loadMastery(courseId: number, version = loadVersion) {
  loading.value = true
  loadError.value = ''
  try {
    const result = await learningApi.getMastery(courseId)
    if (version === loadVersion && selectedCourseId.value === courseId) items.value = result.items
  } catch (error) {
    if (version === loadVersion && selectedCourseId.value === courseId) {
      items.value = []
      loadError.value = pageError(error, '掌握度加载失败')
    }
  } finally {
    if (version === loadVersion && selectedCourseId.value === courseId) loading.value = false
  }
}

async function initialize() {
  const version = ++loadVersion
  selectedCourseId.value = null
  items.value = []
  loadError.value = ''
  await loadCourses()
  if (version !== loadVersion || coursesError.value || !courses.value.length) return
  const requested = queryCourse()
  if (requested.present && (requested.id === null || !courses.value.some((course) => course.id === requested.id))) {
    coursesError.value = 'URL 中的课程不存在、不属于当前账号或已归档'
    return
  }
  const courseId = requested.id || courses.value[0].id
  selectedCourseId.value = courseId
  if (!requested.present) {
    internalRouteUpdate = true
    await router.replace({ name: 'mastery', query: { courseId: String(courseId) } })
    internalRouteUpdate = false
  }
  await loadMastery(courseId, version)
}

async function selectCourse(courseId: number) {
  items.value = []
  loadError.value = ''
  await router.replace({ name: 'mastery', query: { courseId: String(courseId) } })
}

watch(() => route.fullPath, () => {
  if (!internalRouteUpdate) void initialize()
}, { immediate: true })
</script>

<template>
  <div>
    <PageHeader title="知识点掌握度" eyebrow="MASTERY MAP" :description="selectedCourse ? `只展示「${selectedCourse.name}」的真实掌握记录` : '按课程查看真实掌握记录'">
      <el-select :model-value="selectedCourseId" placeholder="选择课程" :loading="coursesLoading" style="width:240px" @change="selectCourse">
        <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
      </el-select>
      <el-button v-if="selectedCourseId" :loading="loading" @click="loadMastery(selectedCourseId)"><el-icon><Refresh /></el-icon>刷新</el-button>
    </PageHeader>

    <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="initialize">重试</el-button></template></el-alert>
    <el-empty v-else-if="!coursesLoading && !courses.length" description="当前账号还没有课程"><el-button type="primary" @click="router.push('/courses')">创建课程</el-button></el-empty>
    <template v-else-if="selectedCourseId">
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="loadMastery(selectedCourseId)">重新加载</el-button></template></el-alert>
      <div v-if="loading" v-loading="true" class="page-loading"></div>
      <template v-else>
        <section class="mastery-summary">
          <div><span>平均掌握度</span><strong>{{ average === null ? '--' : `${average}%` }}</strong><small>仅统计已有真实记录的知识点</small></div>
          <div><span>已有记录</span><strong>{{ recorded.length }}</strong><small>当前课程共 {{ items.length }} 个知识点</small></div>
          <div><span>尚无记录</span><strong>{{ items.length - recorded.length }}</strong><small>不会显示默认初始分数</small></div>
        </section>
        <section class="mastery-grid">
          <article class="content-card card-pad chart-card"><div class="card-header"><div><h2>真实掌握度</h2><p>只绘制已有学习记录的知识点</p></div></div><EChart v-if="recorded.length" :option="chartOption" height="320px" /><el-empty v-else description="当前课程尚无真实掌握记录" /></article>
          <article class="content-card card-pad detail-table">
            <div class="card-header"><div><h2>知识点明细</h2><p>按真实 score 从低到高；无记录项排在末尾</p></div></div>
            <el-table :data="sorted" empty-text="当前课程暂无知识点">
              <el-table-column prop="knowledge_point" label="知识点" min-width="180" />
              <el-table-column label="掌握度" min-width="220"><template #default="scope"><div v-if="scope.row.has_record" class="table-progress"><el-progress :percentage="Math.round(scope.row.score * 100)" :show-text="false" :stroke-width="7" /><span>{{ Math.round(scope.row.score * 100) }}%</span></div><span v-else>--</span></template></el-table-column>
              <el-table-column label="置信度" width="120"><template #default="scope">{{ scope.row.has_record ? `${Math.round(scope.row.confidence * 100)}%` : '--' }}</template></el-table-column>
              <el-table-column label="学习证据" min-width="160"><template #default="scope">{{ scope.row.attempts > 0 ? `${scope.row.attempts} 次尝试` : '尚无学习记录' }}</template></el-table-column>
              <el-table-column label="趋势" width="120"><template #default="scope">{{ scope.row.trend || '暂无趋势' }}</template></el-table-column>
            </el-table>
          </article>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:16px}.page-loading{min-height:360px}.mastery-summary{display:grid;grid-template-columns:repeat(3,1fr);margin-bottom:17px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow-soft);overflow:hidden}.mastery-summary>div{display:flex;flex-direction:column;padding:18px 22px;border-right:1px solid #e9ecf2}.mastery-summary>div:last-child{border:0}.mastery-summary span{color:#8d96a8;font-size:9px}.mastery-summary strong{margin-top:8px;color:#3c4761;font-size:22px}.mastery-summary small{margin-top:6px;color:#9da5b5;font-size:8px}.mastery-grid{display:grid;gap:17px}.chart-card,.detail-table{min-width:0}.table-progress{display:flex;align-items:center;gap:9px}.table-progress .el-progress{width:150px}.table-progress span{font-size:9px}@media(max-width:700px){.mastery-summary{grid-template-columns:1fr}.mastery-summary>div{border-right:0;border-bottom:1px solid #e9ecf2}}
</style>
