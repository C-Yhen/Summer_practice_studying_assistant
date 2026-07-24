import type { Component } from 'vue'
import {
  Calendar,
  ChatDotRound,
  DataAnalysis,
  Finished,
  House,
  MagicStick,
  Reading,
  Setting,
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
    label: '开始学习',
    items: [
      { path: '/dashboard', label: '学习首页', group: '开始学习', keywords: ['首页', '概览', 'dashboard'], icon: House },
      { path: '/today', label: '今日学习', group: '开始学习', keywords: ['今天', '待办', '任务'], icon: Finished },
      { path: '/plan', label: '学习计划', group: '开始学习', keywords: ['计划', '排期', 'ai'], icon: Calendar },
    ],
  },
  {
    label: 'AI 学习',
    items: [
      { path: '/chat', label: 'AI 问答', group: 'AI 学习', keywords: ['问答', '聊天', 'chat', 'ai'], icon: ChatDotRound },
      { path: '/practice', label: '练习与错题', group: 'AI 学习', keywords: ['练习', '答题', '错题', '复习'], icon: Reading },
      { path: '/recommendations', label: '学习建议', group: 'AI 学习', keywords: ['推荐', '建议', '下一步'], icon: MagicStick },
    ],
  },
  {
    label: '我的空间',
    items: [
      { path: '/courses', label: '课程与资料', group: '我的空间', keywords: ['课程', '资料', '文档', '上传', 'course'], icon: Reading },
      { path: '/statistics', label: '学习进度', group: '我的空间', keywords: ['统计', '掌握度', '知识点', '日历', '数据'], icon: DataAnalysis },
      { path: '/settings', label: '个人设置', group: '我的空间', keywords: ['设置', '偏好', '资料'], icon: Setting },
    ],
  },
]

export const navigationItems = navigationGroups.flatMap((group) => group.items)
