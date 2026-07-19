import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/auth/LoginView.vue'), meta: { guest: true, title: '登录' } },
    { path: '/register', name: 'register', component: () => import('@/views/auth/RegisterView.vue'), meta: { guest: true, title: '注册' } },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '学习首页', eyebrow: 'LEARNING OVERVIEW' } },
        { path: 'courses', name: 'courses', component: () => import('@/views/CoursesView.vue'), meta: { title: '课程管理', eyebrow: 'COURSE SPACE' } },
        { path: 'courses/:id', name: 'course-detail', component: () => import('@/views/CourseDetailView.vue'), meta: { title: '课程详情', eyebrow: 'COURSE DETAIL', activeMenu: '/courses' } },
        { path: 'upload', name: 'upload', component: () => import('@/views/UploadView.vue'), meta: { title: '资料上传', eyebrow: 'KNOWLEDGE INGESTION' } },
        { path: 'documents/tasks', name: 'document-tasks', component: () => import('@/views/DocumentProgressView.vue'), meta: { title: '文档处理进度', eyebrow: 'RAG PIPELINE' } },
        { path: 'chat', name: 'chat', component: () => import('@/views/ChatView.vue'), meta: { title: '智能问答', eyebrow: 'RAG ASSISTANT' } },
        { path: 'plan', name: 'plan', component: () => import('@/views/StudyPlanView.vue'), meta: { title: '学习计划', eyebrow: 'ADAPTIVE PLANNING' } },
        { path: 'today', name: 'today', component: () => import('@/views/TodayTasksView.vue'), meta: { title: '今日任务', eyebrow: 'DAILY FOCUS' } },
        { path: 'recommendations', name: 'recommendations', component: () => import('@/views/RecommendationsView.vue'), meta: { title: '推荐中心', eyebrow: 'EXPLAINABLE RECOMMENDATION' } },
        { path: 'practice', name: 'practice', component: () => import('@/views/PracticeView.vue'), meta: { title: '练习答题', eyebrow: 'SMART PRACTICE' } },
        { path: 'wrong-book', name: 'wrong-book', component: () => import('@/views/WrongBookView.vue'), meta: { title: '错题本', eyebrow: 'ERROR REVIEW' } },
        { path: 'mastery', name: 'mastery', component: () => import('@/views/MasteryView.vue'), meta: { title: '知识点掌握度', eyebrow: 'MASTERY MAP' } },
        { path: 'statistics', name: 'statistics', component: () => import('@/views/StatisticsView.vue'), meta: { title: '学习统计', eyebrow: 'LEARNING ANALYTICS' } },
        { path: 'tasks', name: 'tasks', component: () => import('@/views/AsyncTasksView.vue'), meta: { title: '长时任务中心', eyebrow: 'ASYNC JOBS' } },
        { path: 'calendar', name: 'calendar', component: () => import('@/views/CalendarView.vue'), meta: { title: '学习日历', eyebrow: 'LEARNING CALENDAR' } },
        { path: 'settings', name: 'settings', component: () => import('@/views/SettingsView.vue'), meta: { title: '个人设置', eyebrow: 'PREFERENCES' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.restoreSession()
  if (!to.meta.guest && !auth.authenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guest && auth.authenticated) return { name: 'dashboard' }
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '智能学习助手')} · StudyPilot`
})

export default router
