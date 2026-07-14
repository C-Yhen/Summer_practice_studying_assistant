<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Calendar, Document, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { courses as initialCourses } from '@/data/mock'

const router = useRouter()
const search = ref('')
const dialogVisible = ref(false)
const courseList = ref(initialCourses.map((item) => ({ ...item })))
const form = reactive({ name: '', code: '', teacher: '', examDate: '', targetScore: 85 })
const filtered = computed(() => courseList.value.filter((course) => `${course.name}${course.teacher}${course.code}`.toLowerCase().includes(search.value.toLowerCase())))

function createCourse() {
  if (!form.name || !form.examDate) return ElMessage.warning('请填写课程名称与考试日期')
  courseList.value.unshift({ id: Date.now(), name: form.name, code: form.code || 'NEW-2026', teacher: form.teacher || '未设置', color: '#5b6cf9', examDate: form.examDate, progress: 0, documentCount: 0, knowledgeCount: 0, targetScore: form.targetScore })
  dialogVisible.value = false
  ElMessage.success('课程已创建，可以开始上传学习资料')
}
</script>

<template>
  <div>
    <PageHeader title="课程管理" eyebrow="COURSE SPACE" description="把目标、资料、计划与学习记录组织在每一门课程下。">
      <el-button type="primary" @click="dialogVisible = true"><el-icon><Plus /></el-icon>创建课程</el-button>
    </PageHeader>

    <section class="course-overview">
      <div><strong>{{ courseList.length }}</strong><span>进行中课程</span></div><i></i>
      <div><strong>26</strong><span>已入库资料</span></div><i></i>
      <div><strong>89</strong><span>知识点总数</span></div><i></i>
      <div><strong>64%</strong><span>平均掌握度</span></div>
    </section>

    <div class="toolbar">
      <el-input v-model="search" :prefix-icon="Search" placeholder="搜索课程名称、教师或课程编号" clearable style="max-width:340px" />
      <div><el-button plain>全部课程</el-button><el-button text>已归档</el-button></div>
    </div>

    <section class="course-grid">
      <article v-for="course in filtered" :key="course.id" class="course-card" @click="router.push(`/courses/${course.id}`)">
        <div class="course-cover" :style="{ '--course-color': course.color }">
          <span>{{ course.code }}</span><button aria-label="更多操作" @click.stop><el-icon><MoreFilled /></el-icon></button>
          <strong>{{ course.name.slice(0, 1) }}</strong>
        </div>
        <div class="course-body">
          <div class="course-title"><div><h2>{{ course.name }}</h2><p>{{ course.teacher }} · 目标 {{ course.targetScore }} 分</p></div><span>{{ course.progress }}%</span></div>
          <el-progress :percentage="course.progress" :show-text="false" :stroke-width="6" :color="course.color" />
          <div class="course-meta"><span><el-icon><Calendar /></el-icon>{{ course.examDate }} 考试</span><span><el-icon><Document /></el-icon>{{ course.documentCount }} 份资料</span></div>
          <div class="course-footer"><span><i :style="{ background: course.color }"></i>{{ course.knowledgeCount }} 个知识点</span><b>进入课程 →</b></div>
        </div>
      </article>
      <button class="add-course" @click="dialogVisible = true"><span><el-icon><Plus /></el-icon></span><strong>创建新课程</strong><small>设定考试日期与学习目标</small></button>
    </section>

    <el-dialog v-model="dialogVisible" title="创建一门课程" width="min(520px, 92vw)">
      <el-form :model="form" label-position="top">
        <el-form-item label="课程名称（必填）"><el-input v-model="form.name" placeholder="例如：数据库系统" /></el-form-item>
        <div class="form-grid"><el-form-item label="课程编号"><el-input v-model="form.code" placeholder="CS-DB-2026" /></el-form-item><el-form-item label="授课教师"><el-input v-model="form.teacher" placeholder="王老师" /></el-form-item></div>
        <div class="form-grid"><el-form-item label="考试日期（必填）"><el-date-picker v-model="form.examDate" value-format="YYYY-MM-DD" type="date" placeholder="选择日期" style="width:100%" /></el-form-item><el-form-item label="目标成绩"><el-input-number v-model="form.targetScore" :min="60" :max="100" style="width:100%" /></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" @click="createCourse">创建并继续</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.course-overview{display:flex;align-items:center;gap:28px;padding:18px 24px;margin-bottom:22px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:var(--shadow-soft)}.course-overview div{display:flex;align-items:baseline;gap:8px}.course-overview strong{font-size:20px;color:#273250}.course-overview span{color:#8a94a8;font-size:10px}.course-overview i{width:1px;height:25px;background:#e9ecf2}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-bottom:18px}.course-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.course-card{overflow:hidden;border:1px solid var(--line);border-radius:18px;background:white;box-shadow:var(--shadow-soft);cursor:pointer;transition:.2s ease}.course-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-card)}.course-cover{position:relative;height:105px;padding:16px 18px;overflow:hidden;background:linear-gradient(135deg,var(--course-color),color-mix(in srgb,var(--course-color),#111b3c 22%));color:white}.course-cover::before,.course-cover::after{content:"";position:absolute;border:1px solid rgba(255,255,255,.15);border-radius:50%}.course-cover::before{width:140px;height:140px;right:-25px;top:-78px}.course-cover::after{width:80px;height:80px;right:35px;bottom:-53px}.course-cover>span{font-size:9px;letter-spacing:1px;opacity:.78}.course-cover>strong{position:absolute;right:22px;bottom:4px;font-size:64px;line-height:1;color:rgba(255,255,255,.11)}.course-cover button{float:right;border:0;background:transparent;color:white;cursor:pointer}.course-body{padding:17px}.course-title{display:flex;justify-content:space-between;gap:10px;margin-bottom:13px}.course-title h2{margin:0;color:#303b58;font-size:15px}.course-title p{margin:6px 0 0;color:#919aae;font-size:9px}.course-title>span{color:var(--course-color,#5b6cf9);font-size:12px;font-weight:700}.course-meta{display:flex;gap:16px;margin:13px 0;color:#818ca3;font-size:9px}.course-meta span{display:flex;align-items:center;gap:5px}.course-footer{display:flex;align-items:center;justify-content:space-between;padding-top:12px;border-top:1px solid #edf0f4;color:#818ba0;font-size:9px}.course-footer span{display:flex;align-items:center;gap:6px}.course-footer i{width:6px;height:6px;border-radius:50%}.course-footer b{color:var(--brand);font-size:9px}.add-course{min-height:270px;display:flex;align-items:center;justify-content:center;flex-direction:column;border:1.5px dashed #cfd6e5;border-radius:18px;background:rgba(255,255,255,.55);color:#7d88a0;cursor:pointer}.add-course:hover{border-color:#8d98ee;background:#f9f9ff}.add-course>span{width:43px;height:43px;display:grid;place-items:center;border-radius:13px;background:#edf0ff;color:#6473e8;font-size:19px}.add-course strong{margin-top:13px;color:#4d5872;font-size:12px}.add-course small{margin-top:7px;font-size:9px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:1100px){.course-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.course-overview{display:grid;grid-template-columns:1fr 1fr}.course-overview i{display:none}.course-overview div{flex-direction:column;gap:3px}.toolbar{align-items:flex-start;flex-direction:column}.course-grid{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}}
</style>
