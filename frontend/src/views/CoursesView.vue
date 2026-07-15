<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Calendar, Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { courseApi } from '@/api/services'
import type { CourseCreateRequest, CourseListItem } from '@/types'

const DEFAULT_COLOR = '#5b6cf9'
const router = useRouter()
const search = ref('')
const dialogVisible = ref(false)
const loading = ref(false)
const creating = ref(false)
const loadError = ref('')
const total = ref(0)
const courseList = ref<CourseListItem[]>([])
const form = reactive({
  name: '',
  code: '',
  description: '',
  examDate: '',
  targetScore: 85,
})

const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return courseList.value
  return courseList.value.filter((course) => (
    `${course.name} ${course.code || ''} ${course.description || ''}`.toLowerCase().includes(keyword)
  ))
})

function resetForm() {
  form.name = ''
  form.code = ''
  form.description = ''
  form.examDate = ''
  form.targetScore = 85
}

function getCourseErrorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

async function loadCourses() {
  loading.value = true
  loadError.value = ''
  try {
    const result = await courseApi.list()
    courseList.value = result.items
    total.value = result.total
  } catch (error) {
    courseList.value = []
    total.value = 0
    loadError.value = getCourseErrorMessage(error, '课程列表加载失败')
  } finally {
    loading.value = false
  }
}

async function createCourse() {
  const name = form.name.trim()
  if (!name) return ElMessage.warning('请填写课程名称')

  const payload: CourseCreateRequest = {
    name,
    code: form.code.trim() || null,
    description: form.description.trim() || null,
    exam_date: form.examDate || null,
    target_score: form.targetScore,
    color: DEFAULT_COLOR,
  }
  creating.value = true
  try {
    const created = await courseApi.create(payload)
    courseList.value.unshift(created)
    total.value += 1
    dialogVisible.value = false
    resetForm()
    ElMessage.success('课程已创建')
  } catch (error) {
    ElMessage.error(getCourseErrorMessage(error, '课程创建失败'))
  } finally {
    creating.value = false
  }
}

onMounted(loadCourses)
</script>

<template>
  <div>
    <PageHeader title="课程管理" eyebrow="COURSE SPACE" description="把目标、资料、计划与学习记录组织在每一门课程下。">
      <el-button type="primary" @click="dialogVisible = true"><el-icon><Plus /></el-icon>创建课程</el-button>
    </PageHeader>

    <section class="course-overview">
      <div><strong>{{ total }}</strong><span>当前课程</span></div>
    </section>

    <div class="toolbar">
      <el-input v-model="search" :prefix-icon="Search" placeholder="搜索课程名称、编号或描述" clearable style="max-width:380px" />
    </div>

    <el-alert v-if="loadError" class="load-alert" :title="loadError" type="error" :closable="false" show-icon>
      <template #default><el-button size="small" @click="loadCourses">重新加载</el-button></template>
    </el-alert>

    <section v-else v-loading="loading" class="list-shell">
      <div v-if="filtered.length" class="course-grid">
        <article v-for="course in filtered" :key="course.id" class="course-card" @click="router.push(`/courses/${course.id}`)">
          <div class="course-cover" :style="{ '--course-color': course.color }">
            <span>{{ course.code || '未设置编号' }}</span>
            <strong>{{ course.name.slice(0, 1) }}</strong>
          </div>
          <div class="course-body">
            <div class="course-title">
              <div><h2>{{ course.name }}</h2><p>目标 {{ course.targetScore }} 分</p></div>
            </div>
            <p class="course-description">{{ course.description || '暂无课程描述' }}</p>
            <div class="course-meta"><span><el-icon><Calendar /></el-icon>{{ course.examDate ? `${course.examDate} 考试` : '未设置考试日期' }}</span></div>
            <div class="course-footer"><span><i :style="{ background: course.color }"></i>{{ course.archived ? '已归档' : '进行中' }}</span><b>进入课程 →</b></div>
          </div>
        </article>
        <button v-if="!search" class="add-course" @click="dialogVisible = true"><span><el-icon><Plus /></el-icon></span><strong>创建新课程</strong><small>考试日期可以稍后设置</small></button>
      </div>
      <el-empty v-else-if="!loading" :description="search ? '没有匹配的课程' : '还没有课程'">
        <el-button v-if="!search" type="primary" @click="dialogVisible = true">创建第一门课程</el-button>
      </el-empty>
    </section>

    <el-dialog v-model="dialogVisible" title="创建一门课程" width="min(520px, 92vw)" :close-on-click-modal="!creating">
      <el-form :model="form" label-position="top" @keyup.enter="createCourse">
        <el-form-item label="课程名称（必填）"><el-input v-model="form.name" maxlength="160" placeholder="例如：数据库系统" /></el-form-item>
        <el-form-item label="课程编号"><el-input v-model="form.code" maxlength="50" placeholder="例如：CS-DB-2026" /></el-form-item>
        <el-form-item label="课程描述"><el-input v-model="form.description" type="textarea" :rows="3" maxlength="5000" show-word-limit placeholder="可选，记录课程范围或学习目标" /></el-form-item>
        <div class="form-grid">
          <el-form-item label="考试日期（可选）"><el-date-picker v-model="form.examDate" value-format="YYYY-MM-DD" type="date" placeholder="选择日期" style="width:100%" /></el-form-item>
          <el-form-item label="目标成绩"><el-input-number v-model="form.targetScore" :min="0" :max="100" style="width:100%" /></el-form-item>
        </div>
      </el-form>
      <template #footer><el-button :disabled="creating" @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="creating" :disabled="creating" @click="createCourse">创建课程</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.course-overview{display:flex;align-items:center;padding:18px 24px;margin-bottom:22px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow-soft)}.course-overview div{display:flex;align-items:baseline;gap:8px}.course-overview strong{font-size:20px;color:#273250}.course-overview span{color:#8a94a8;font-size:10px}.toolbar{display:flex;align-items:center;margin-bottom:18px}.load-alert{margin-bottom:18px}.load-alert :deep(.el-alert__content){width:100%}.load-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.list-shell{min-height:260px}.course-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.course-card{overflow:hidden;border:1px solid var(--line);border-radius:18px;background:white;box-shadow:var(--shadow-soft);cursor:pointer;transition:.2s ease}.course-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-card)}.course-cover{position:relative;height:105px;padding:16px 18px;overflow:hidden;background:linear-gradient(135deg,var(--course-color),color-mix(in srgb,var(--course-color),#111b3c 22%));color:white}.course-cover::before,.course-cover::after{content:"";position:absolute;border:1px solid rgba(255,255,255,.15);border-radius:50%}.course-cover::before{width:140px;height:140px;right:-25px;top:-78px}.course-cover::after{width:80px;height:80px;right:35px;bottom:-53px}.course-cover>span{font-size:9px;letter-spacing:1px;opacity:.78}.course-cover>strong{position:absolute;right:22px;bottom:4px;font-size:64px;line-height:1;color:rgba(255,255,255,.11)}.course-body{padding:17px}.course-title{display:flex;justify-content:space-between;gap:10px;margin-bottom:12px}.course-title h2{margin:0;color:#303b58;font-size:15px}.course-title p{margin:6px 0 0;color:#6975dc;font-size:9px}.course-description{height:34px;display:-webkit-box;overflow:hidden;margin:0;color:#858fa4;font-size:9px;line-height:1.8;-webkit-box-orient:vertical;-webkit-line-clamp:2}.course-meta{display:flex;margin:13px 0;color:#818ca3;font-size:9px}.course-meta span{display:flex;align-items:center;gap:5px}.course-footer{display:flex;align-items:center;justify-content:space-between;padding-top:12px;border-top:1px solid #edf0f4;color:#818ba0;font-size:9px}.course-footer span{display:flex;align-items:center;gap:6px}.course-footer i{width:6px;height:6px;border-radius:50%}.course-footer b{color:var(--brand);font-size:9px}.add-course{min-height:270px;display:flex;align-items:center;justify-content:center;flex-direction:column;border:1.5px dashed #cfd6e5;border-radius:18px;background:rgba(255,255,255,.55);color:#7d88a0;cursor:pointer}.add-course:hover{border-color:#8d98ee;background:#f9f9ff}.add-course>span{width:43px;height:43px;display:grid;place-items:center;border-radius:13px;background:#edf0ff;color:#6473e8;font-size:19px}.add-course strong{margin-top:13px;color:#4d5872;font-size:12px}.add-course small{margin-top:7px;font-size:9px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:1100px){.course-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.course-grid{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}}
</style>
