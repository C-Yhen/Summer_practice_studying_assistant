import type { AsyncTask, Citation, Course, StudyTask } from '@/types'

export const courses: Course[] = [
  { id: 1, name: '数据库系统', code: 'CS-DB-2026', teacher: '王老师', color: '#5b6cf9', examDate: '2026-07-21', progress: 68, documentCount: 12, knowledgeCount: 34, targetScore: 90 },
  { id: 2, name: '计算机网络', code: 'CS-NET-2026', teacher: '李老师', color: '#18a88c', examDate: '2026-07-28', progress: 52, documentCount: 7, knowledgeCount: 24, targetScore: 85 },
  { id: 3, name: '操作系统', code: 'CS-OS-2026', teacher: '陈老师', color: '#ef974b', examDate: '2026-08-03', progress: 43, documentCount: 5, knowledgeCount: 19, targetScore: 88 },
  { id: 4, name: '软件工程', code: 'SE-2026', teacher: '周老师', color: '#9b6ce3', examDate: '2026-08-10', progress: 36, documentCount: 2, knowledgeCount: 12, targetScore: 85 },
]

export const todayTasks: StudyTask[] = [
  { id: 1, title: '复习函数依赖与属性闭包', course: '数据库系统', type: '复习', duration: 25, priority: '高', status: 'done', knowledge: '函数依赖' },
  { id: 2, title: '完成第三范式判断练习', course: '数据库系统', type: '练习', duration: 30, priority: '高', status: 'doing', knowledge: '第三范式' },
  { id: 3, title: '阅读数据库索引讲义', course: '数据库系统', type: '阅读', duration: 25, priority: '中', status: 'todo', knowledge: 'B+ 树索引' },
  { id: 4, title: '完成每日知识点测试', course: '数据库系统', type: '测试', duration: 20, priority: '中', status: 'todo', knowledge: '关系模型' },
  { id: 5, title: '复习 TCP 拥塞控制', course: '计算机网络', type: '复习', duration: 20, priority: '低', status: 'todo', knowledge: '拥塞控制' },
]

export const citations: Citation[] = [
  { id: 1, document: '数据库系统课程讲义.pdf', page: 42, chapter: '第 4 章 关系规范化', snippet: '第三范式要求非主属性不传递依赖于任何候选码。', score: 0.96 },
  { id: 2, document: '期末复习重点.md', page: 7, chapter: '范式判断', snippet: '判断 3NF 时，先求候选码，再区分主属性与非主属性。', score: 0.92 },
  { id: 3, document: '数据库习题解析.pdf', page: 18, chapter: '依赖分解', snippet: '通过无损连接分解可以消除传递依赖造成的数据冗余。', score: 0.88 },
]

export const asyncTasks: AsyncTask[] = [
  { id: 'job-240714-01', name: '数据库课程讲义入库', type: '文档处理', status: 'success', progress: 100, step: '已生成 186 个文档块', createdAt: '2026-07-14 09:20' },
  { id: 'job-240714-02', name: '知识点掌握度重算', type: '学习分析', status: 'processing', progress: 72, step: '正在计算依赖关系', createdAt: '2026-07-14 10:05' },
  { id: 'job-240714-03', name: '今日学习计划生成', type: '计划生成', status: 'success', progress: 100, step: '已生成 5 项学习任务', createdAt: '2026-07-14 08:30' },
  { id: 'job-240714-04', name: '错题集归纳', type: '内容生成', status: 'queued', progress: 0, step: '等待 Worker 处理', createdAt: '2026-07-14 10:18' },
]

export const knowledgeMastery = [
  { name: 'SQL 基础', value: 86, trend: 5 },
  { name: '关系代数', value: 74, trend: 3 },
  { name: '函数依赖', value: 52, trend: -2 },
  { name: '候选码', value: 47, trend: 4 },
  { name: '第三范式', value: 43, trend: -3 },
  { name: '事务与并发', value: 68, trend: 6 },
]

export const trendData = [
  { day: '周一', minutes: 92, completion: 68 },
  { day: '周二', minutes: 118, completion: 75 },
  { day: '周三', minutes: 76, completion: 64 },
  { day: '周四', minutes: 132, completion: 86 },
  { day: '周五', minutes: 105, completion: 81 },
  { day: '周六', minutes: 148, completion: 92 },
  { day: '周日', minutes: 119, completion: 82 },
]
