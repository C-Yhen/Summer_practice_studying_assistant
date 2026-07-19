import type { Component } from 'vue'
import {
  Calendar,
  ChatDotRound,
  Collection,
  DataAnalysis,
  Document,
  Files,
  Finished,
  House,
  MagicStick,
  Notebook,
  Reading,
  Setting,
  TrendCharts,
  UploadFilled,
} from '@element-plus/icons-vue'

export interface NavigationItem {
  path: string
  label: string
  group: string
  keywords: string[]
  icon: Component
}

export interface NavigationGroup {
  label: string
  items: NavigationItem[]
}

export const navigationGroups: NavigationGroup[] = [
  {
    label: '学习工作台',
    items: [
      { path: '/dashboard', label: '学习首页', group: '学习工作台', keywords: ['首页', '概览', 'dashboard'], icon: House },
      { path: '/today', label: '今日任务', group: '学习工作台', keywords: ['今天', '待办', '任务'], icon: Finished },
      { path: '/plan', label: '学习计划', group: '学习工作台', keywords: ['计划', '排期'], icon: Calendar },
    ],
  },
  {
    label: '课程与知识库',
    items: [
      { path: '/courses', label: '课程管理', group: '课程与知识库', keywords: ['课程', 'course'], icon: Collection },
      { path: '/upload', label: '资料上传', group: '课程与知识库', keywords: ['上传', '资料', '文档'], icon: UploadFilled },
      { path: '/documents/tasks', label: '处理进度', group: '课程与知识库', keywords: ['文档处理', '解析', '进度'], icon: Document },
    ],
  },
  {
    label: '智能学习',
    items: [
      { path: '/chat', label: '智能问答', group: '智能学习', keywords: ['问答', '聊天', 'chat'], icon: ChatDotRound },
      { path: '/recommendations', label: '推荐中心', group: '智能学习', keywords: ['推荐', '建议'], icon: MagicStick },
      { path: '/practice', label: '练习答题', group: '智能学习', keywords: ['练习', '答题', '题目'], icon: Reading },
      { path: '/wrong-book', label: '错题本', group: '智能学习', keywords: ['错题', '复习'], icon: Notebook },
    ],
  },
  {
    label: '洞察与工具',
    items: [
      { path: '/mastery', label: '知识点掌握度', group: '洞察与工具', keywords: ['掌握度', '知识点', '能力'], icon: TrendCharts },
      { path: '/statistics', label: '学习统计', group: '洞察与工具', keywords: ['统计', '数据', '分析'], icon: DataAnalysis },
      { path: '/tasks', label: '长时任务中心', group: '洞察与工具', keywords: ['异步任务', '任务中心', '处理任务'], icon: Files },
      { path: '/calendar', label: '学习日历', group: '洞察与工具', keywords: ['日历', '日程', 'calendar'], icon: Calendar },
      { path: '/settings', label: '个人设置', group: '洞察与工具', keywords: ['设置', '偏好', '资料'], icon: Setting },
    ],
  },
]

export const navigationItems = navigationGroups.flatMap((group) => group.items)
