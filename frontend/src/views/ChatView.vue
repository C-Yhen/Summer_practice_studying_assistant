<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, CirclePlus, Document, Promotion, Search, Upload, User } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getApiErrorMessage, isUnauthorizedError } from '@/api/client'
import { chatApi, courseApi, documentApi } from '@/api/services'
import { renderLatex } from '@/utils/katex'
import type { AIRuntimeStatus, BackendDocument, ChatMessage, ChatSession, CourseListItem, RagCitation } from '@/types'

const route = useRoute()
const router = useRouter()
const courses = ref<CourseListItem[]>([])
const selectedCourseId = ref<number | null>(null)
const coursesLoading = ref(false)
const coursesError = ref('')
const documents = ref<BackendDocument[]>([])
const documentsLoading = ref(false)
const documentsError = ref('')
const selectedDocumentIds = ref<number[]>([])
const sessions = ref<ChatSession[]>([])
const sessionsLoading = ref(false)
const sessionsError = ref('')
const sessionSearch = ref('')
const activeSessionId = ref('')
const messages = ref<ChatMessage[]>([])
const messagesLoading = ref(false)
const messagesError = ref('')
const activeCitations = ref<RagCitation[]>([])
const question = ref('')
const pendingQuestion = ref('')
const sending = ref(false)
const messageArea = ref<HTMLElement>()
const aiRuntime = ref<AIRuntimeStatus | null>(null)
const aiRuntimeError = ref('')
const suggestions = ['总结所选资料的核心内容', '列出三个复习重点并说明依据', '用通俗语言解释一个关键概念']
let initializationVersion = 0
let internalRouteUpdate = false

const selectedCourse = computed(() => courses.value.find((course) => course.id === selectedCourseId.value) || null)
const readyDocuments = computed(() => documents.value.filter((document) => document.status === 'ready'))
const pendingDocumentCount = computed(() => documents.value.length - readyDocuments.value.length)
const filteredSessions = computed(() => {
  const keyword = sessionSearch.value.trim().toLowerCase()
  return keyword
    ? sessions.value.filter((session) => session.title.toLowerCase().includes(keyword))
    : sessions.value
})
const scopeLabel = computed(() => {
  if (!readyDocuments.value.length) return '暂无已就绪资料'
  if (!selectedDocumentIds.value.length) return `全部 ${readyDocuments.value.length} 份已就绪资料`
  return `已选择 ${selectedDocumentIds.value.length} 份资料`
})
const canSend = computed(() => (
  selectedCourseId.value !== null
  && readyDocuments.value.length > 0
  && Boolean(question.value.trim())
  && !sending.value
))
const assistantName = computed(() => aiRuntime.value?.is_mock ? '本地演示助教' : '课程助教')
const assistantAvatar = computed(() => aiRuntime.value?.is_mock ? 'DEMO' : 'AI')
const runtimeLabel = computed(() => {
  if (aiRuntimeError.value) return 'AI 状态不可用'
  if (!aiRuntime.value) return '正在确认模型状态'
  if (aiRuntime.value.is_mock) return '本地 Mock · 非真实模型'
  return `${aiRuntime.value.provider} · ${aiRuntime.value.chat_model}`
})
const runtimeDetail = computed(() => {
  if (!aiRuntime.value) return ''
  return aiRuntime.value.embedding_mode === 'local' ? '本地检索向量' : '远程检索向量'
})

function parseCourseId(value: unknown): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = typeof raw === 'string' ? Number(raw) : NaN
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function parseSessionId(value: unknown): string {
  const raw = Array.isArray(value) ? value[0] : value
  return typeof raw === 'string' ? raw.trim() : ''
}

function chatErrorMessage(error: unknown, fallback: string) {
  return isUnauthorizedError(error) ? '登录状态已失效，请重新登录' : getApiErrorMessage(error, fallback)
}

async function syncUrl(sessionId = activeSessionId.value) {
  if (!selectedCourseId.value) return
  internalRouteUpdate = true
  try {
    await router.replace({
      name: 'chat',
      query: {
        courseId: String(selectedCourseId.value),
        ...(sessionId ? { sessionId } : {}),
      },
    })
  } finally {
    internalRouteUpdate = false
  }
}

function resetConversation() {
  activeSessionId.value = ''
  messages.value = []
  messagesError.value = ''
  activeCitations.value = []
  pendingQuestion.value = ''
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = ''
  try {
    const result = await courseApi.list()
    courses.value = result.items.filter((course) => !course.archived)
  } catch (error) {
    courses.value = []
    coursesError.value = chatErrorMessage(error, '课程列表加载失败')
  } finally {
    coursesLoading.value = false
  }
}

async function loadAIRuntime() {
  aiRuntimeError.value = ''
  try {
    aiRuntime.value = await chatApi.runtimeStatus()
  } catch (error) {
    aiRuntime.value = null
    aiRuntimeError.value = chatErrorMessage(error, '无法确认 AI 模型状态')
  }
}

async function loadDocuments(courseId: number) {
  documentsLoading.value = true
  documentsError.value = ''
  try {
    const result = await documentApi.list(courseId)
    if (selectedCourseId.value === courseId) documents.value = result.items
  } catch (error) {
    if (selectedCourseId.value === courseId) {
      documents.value = []
      documentsError.value = chatErrorMessage(error, '课程资料加载失败')
    }
  } finally {
    if (selectedCourseId.value === courseId) documentsLoading.value = false
  }
}

async function loadSessions(courseId: number) {
  sessionsLoading.value = true
  sessionsError.value = ''
  try {
    const result = await chatApi.listSessions(courseId)
    if (selectedCourseId.value === courseId) sessions.value = result.items
  } catch (error) {
    if (selectedCourseId.value === courseId) {
      sessions.value = []
      sessionsError.value = chatErrorMessage(error, '历史会话加载失败')
    }
  } finally {
    if (selectedCourseId.value === courseId) sessionsLoading.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  messageArea.value?.scrollTo({ top: messageArea.value.scrollHeight, behavior: 'smooth' })
}

async function loadMessages(sessionId: string) {
  messagesLoading.value = true
  messagesError.value = ''
  try {
    const result = await chatApi.listMessages(sessionId)
    if (activeSessionId.value !== sessionId) return
    messages.value = result.items
    const lastAssistant = [...result.items].reverse().find((message) => message.role === 'assistant')
    activeCitations.value = lastAssistant?.citations || []
    await scrollToBottom()
  } catch (error) {
    if (activeSessionId.value === sessionId) {
      messages.value = []
      activeCitations.value = []
      messagesError.value = chatErrorMessage(error, '消息记录加载失败')
    }
  } finally {
    if (activeSessionId.value === sessionId) messagesLoading.value = false
  }
}

async function initialize() {
  const version = ++initializationVersion
  selectedCourseId.value = null
  documents.value = []
  selectedDocumentIds.value = []
  sessions.value = []
  resetConversation()
  await Promise.all([loadCourses(), loadAIRuntime()])
  if (version !== initializationVersion || coursesError.value) return

  const rawCourseId = route.query.courseId
  const courseId = parseCourseId(rawCourseId)
  if (!courseId) {
    if (rawCourseId !== undefined) coursesError.value = 'URL 中的课程地址无效'
    return
  }
  if (!courses.value.some((course) => course.id === courseId)) {
    coursesError.value = 'URL 中的课程不属于当前账号或已归档'
    return
  }
  selectedCourseId.value = courseId
  await Promise.all([loadDocuments(courseId), loadSessions(courseId)])
  if (version !== initializationVersion) return

  const sessionId = parseSessionId(route.query.sessionId)
  if (!sessionId) return
  const session = sessions.value.find((item) => item.session_id === sessionId)
  if (!session) {
    sessionsError.value = 'URL 中的会话不属于当前课程或已不可用'
    return
  }
  activeSessionId.value = sessionId
  const readyIds = new Set(readyDocuments.value.map((document) => document.id))
  selectedDocumentIds.value = session.document_ids.filter((documentId) => readyIds.has(documentId))
  await loadMessages(sessionId)
}

async function selectCourse(courseId: number) {
  initializationVersion += 1
  selectedCourseId.value = courseId
  documents.value = []
  selectedDocumentIds.value = []
  sessions.value = []
  resetConversation()
  await syncUrl('')
  await Promise.all([loadDocuments(courseId), loadSessions(courseId)])
}

async function selectSession(session: ChatSession) {
  activeSessionId.value = session.session_id
  messages.value = []
  messagesError.value = ''
  activeCitations.value = []
  const readyIds = new Set(readyDocuments.value.map((document) => document.id))
  selectedDocumentIds.value = session.document_ids.filter((documentId) => readyIds.has(documentId))
  await syncUrl(session.session_id)
  await loadMessages(session.session_id)
}

async function newChat() {
  resetConversation()
  selectedDocumentIds.value = []
  await syncUrl('')
}

async function changeDocumentScope() {
  if (!activeSessionId.value) return
  resetConversation()
  await syncUrl('')
}

async function send(text = question.value) {
  const value = text.trim()
  if (!value || sending.value) return
  if (!selectedCourseId.value) return ElMessage.warning('请先选择课程')
  if (!readyDocuments.value.length) return ElMessage.warning('当前课程还没有已就绪资料')

  sending.value = true
  pendingQuestion.value = value
  try {
    let sessionId = activeSessionId.value
    if (!sessionId) {
      const created = await chatApi.createSession(selectedCourseId.value, {
        title: '新对话',
        mode: 'strict',
        document_ids: selectedDocumentIds.value,
      })
      sessionId = created.session_id
      activeSessionId.value = sessionId
      await syncUrl(sessionId)
    }

    const result = await chatApi.ask(sessionId, {
      question: value,
      mode: 'strict',
      document_ids: selectedDocumentIds.value,
      top_k: 5,
    })
    question.value = ''
    activeCitations.value = result.citations
    await Promise.all([loadMessages(sessionId), loadSessions(selectedCourseId.value)])
    if (messagesError.value) {
      const timestamp = new Date().toISOString()
      messages.value = [
        ...messages.value,
        { id: `local-user-${timestamp}`, role: 'user', content: value, citations: [], sufficient_evidence: null, created_at: timestamp },
        { id: result.message_id, role: 'assistant', content: result.answer, citations: result.citations, sufficient_evidence: result.sufficient_evidence, created_at: timestamp },
      ]
    }
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(chatErrorMessage(error, '问答请求失败'))
  } finally {
    pendingQuestion.value = ''
    sending.value = false
  }
}

function showSources(message: ChatMessage) {
  activeCitations.value = message.citations
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

watch(() => route.fullPath, () => {
  if (!internalRouteUpdate) void initialize()
}, { immediate: true })
</script>

<template>
  <div class="chat-page">
    <PageHeader title="资料问答" eyebrow="基于课程资料" description="向自己的课程资料提问。每个回答都会标明证据是否充分，并提供可核对的原文引用。">
      <el-select :model-value="selectedCourseId" placeholder="选择课程" :loading="coursesLoading" style="width:240px" @change="selectCourse">
        <el-option v-for="course in courses" :key="course.id" :value="course.id" :label="course.code ? `${course.name} · ${course.code}` : course.name" />
      </el-select>
    </PageHeader>

    <el-alert v-if="coursesError" :title="coursesError" type="error" :closable="false" show-icon class="page-alert"><template #default><el-button size="small" @click="initialize">重新加载</el-button></template></el-alert>
    <el-empty v-else-if="!coursesLoading && !courses.length" description="当前账号还没有课程"><el-button type="primary" @click="router.push('/courses')">创建课程</el-button></el-empty>
    <el-empty v-else-if="!selectedCourseId" description="请选择一门课程开始问答" />

    <section v-else class="chat-shell content-card">
      <aside class="session-panel">
        <el-button type="primary" class="new-chat" @click="newChat"><el-icon><CirclePlus /></el-icon>新建对话</el-button>
        <div class="session-search"><el-icon><Search /></el-icon><input v-model="sessionSearch" placeholder="搜索历史对话" /></div>
        <span class="session-label">历史会话</span>
        <div v-if="sessionsLoading" v-loading="true" class="session-loading"></div>
        <el-alert v-else-if="sessionsError" :title="sessionsError" type="error" :closable="false" class="compact-alert"><template #default><el-button size="small" @click="loadSessions(selectedCourseId)">重试</el-button></template></el-alert>
        <div v-else-if="!filteredSessions.length" class="session-empty">{{ sessionSearch ? '没有匹配的会话' : '还没有历史会话' }}</div>
        <button v-for="item in filteredSessions" v-else :key="item.session_id" class="session-item" :class="{ active: activeSessionId === item.session_id }" @click="selectSession(item)"><el-icon><ChatDotRound /></el-icon><span><b>{{ item.title }}</b><small>{{ formatTime(item.updated_at) }}</small></span></button>
        <div class="rag-scope"><span><i></i>{{ readyDocuments.length ? '资料范围可用' : '资料尚未就绪' }}</span><b>{{ readyDocuments.length }} 份已就绪资料</b><small v-if="pendingDocumentCount">另有 {{ pendingDocumentCount }} 份正在处理或失败</small><small v-else>只检索当前课程有效版本</small></div>
      </aside>

      <main class="conversation">
        <div class="conversation-head"><div><span class="ai-avatar" :class="{ demo: aiRuntime?.is_mock }">{{ assistantAvatar }}</span><p><b>{{ assistantName }}</b><small><i :class="{ warning: aiRuntime?.is_mock || aiRuntimeError }"></i>{{ selectedCourse?.name }}</small></p></div><div class="runtime-status"><span class="model-pill" :class="{ demo: aiRuntime?.is_mock, error: aiRuntimeError }">{{ runtimeLabel }}</span><small v-if="runtimeDetail">{{ runtimeDetail }} · 回答仅依据课程资料</small></div></div>

        <el-alert v-if="aiRuntime?.is_mock" title="当前为本地 Mock 演示模式，回答由固定规则生成，不是 DeepSeek 或其他真实大模型输出。" type="warning" :closable="false" show-icon class="runtime-alert" />
        <el-alert v-else-if="aiRuntimeError" :title="aiRuntimeError" type="error" :closable="false" show-icon class="runtime-alert"><template #default><el-button size="small" @click="loadAIRuntime">重新检查</el-button></template></el-alert>

        <el-alert v-if="documentsError" :title="documentsError" type="error" :closable="false" show-icon class="inner-alert"><template #default><el-button size="small" @click="loadDocuments(selectedCourseId)">重新加载资料</el-button></template></el-alert>
        <div v-else-if="documentsLoading" v-loading="true" class="documents-loading"></div>
        <div v-else-if="!readyDocuments.length" class="no-documents"><el-empty :description="documents.length ? '资料尚未处理完成' : '当前课程还没有资料'"><el-button type="primary" :icon="Upload" @click="router.push({ name: 'upload', query: { courseId: String(selectedCourseId) } })">上传资料</el-button><el-button @click="loadDocuments(selectedCourseId)">刷新状态</el-button></el-empty></div>

        <template v-else>
          <div ref="messageArea" v-loading="messagesLoading" class="messages">
            <el-alert v-if="messagesError" :title="messagesError" type="error" :closable="false" show-icon class="inner-alert"><template #default><el-button v-if="activeSessionId" size="small" @click="loadMessages(activeSessionId)">重新加载消息</el-button></template></el-alert>
            <div v-if="!messagesLoading && !messages.length && !messagesError" class="chat-welcome"><span :class="{ demo: aiRuntime?.is_mock }">{{ assistantAvatar }}</span><h2>从课程资料开始提问</h2><p>你可以让{{ assistantName }}解释概念、总结章节或梳理复习重点。回答中的引用可在右侧逐条核对。</p></div>
            <div v-for="message in messages" :key="message.id" class="message" :class="message.role">
              <span class="message-avatar" :class="{ demo: message.role === 'assistant' && aiRuntime?.is_mock }"><el-icon v-if="message.role === 'user'"><User /></el-icon><template v-else>{{ assistantAvatar }}</template></span>
              <div class="message-block">
                <div class="message-meta"><b>{{ message.role === 'user' ? '你' : assistantName }}</b><span>{{ formatTime(message.created_at) }}</span><em v-if="message.role === 'assistant'" :class="{ enough: message.sufficient_evidence !== false }">{{ message.sufficient_evidence === false ? '证据不足，请谨慎使用' : '已有资料依据' }}</em></div>
                <div class="bubble math-content" v-html="renderLatex(message.content)"></div>
                <div v-if="message.citations.length" class="answer-tools"><button @click="showSources(message)"><el-icon><Document /></el-icon>查看 {{ message.citations.length }} 条原文依据</button></div>
              </div>
            </div>
            <div v-if="sending" class="message assistant"><span class="message-avatar" :class="{ demo: aiRuntime?.is_mock }">{{ assistantAvatar }}</span><div class="message-block"><div class="message-meta"><b>{{ assistantName }}</b><span>正在检索课程资料</span></div><div class="typing"><i></i><i></i><i></i><span>正在查找相关原文并组织回答…</span></div><small class="pending-question">正在回答：{{ pendingQuestion }}</small></div></div>
          </div>

          <div class="composer-wrap">
            <div class="scope-select"><span>检索范围</span><el-select v-model="selectedDocumentIds" multiple collapse-tags collapse-tags-tooltip clearable placeholder="全部已就绪资料" :disabled="sending" @change="changeDocumentScope"><el-option v-for="document in readyDocuments" :key="document.id" :value="document.id" :label="document.title" /></el-select></div>
            <div class="suggestions"><button v-for="item in suggestions" :key="item" :disabled="sending" @click="send(item)">{{ item }}</button></div>
            <div class="composer"><textarea v-model="question" rows="2" maxlength="4000" :disabled="sending" placeholder="向课程资料提问，Shift + Enter 换行…" @keydown.enter.exact.prevent="send()"></textarea><div><span>{{ scopeLabel }}</span><button :disabled="!canSend" aria-label="发送问题" @click="send()"><el-icon><Promotion /></el-icon></button></div></div>
            <p>重要结论请结合右侧原文依据核对；资料没有覆盖时，课程助教会明确提示证据不足。</p>
          </div>
        </template>
      </main>

      <aside class="sources-panel">
        <div class="sources-head"><div><h2>引用来源</h2><p>{{ activeCitations.length }} 条内容支持当前答案</p></div></div>
        <el-empty v-if="!activeCitations.length" description="选择一条带引用的回答查看来源" :image-size="70" />
        <div v-else class="source-list"><article v-for="source in activeCitations" :key="source.source_id"><div class="source-top"><span>{{ source.source_id }}</span><strong>{{ Math.round(source.score * 100) }}% 相关</strong></div><h3>{{ source.document_name }}</h3><p class="source-location"><el-icon><Document /></el-icon>{{ source.page_number === null ? '未标注页码' : `第 ${source.page_number} 页` }} · {{ source.chapter_name || '未识别章节' }}</p><blockquote>{{ source.quote }}</blockquote><small>文档 #{{ source.document_id }} · 版本 {{ source.document_version }} · 文本块 #{{ source.chunk_id }}</small></article></div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.page-alert{margin-bottom:18px}.page-alert :deep(.el-alert__content),.inner-alert :deep(.el-alert__content),.compact-alert :deep(.el-alert__content){width:100%}.page-alert :deep(.el-alert__description),.inner-alert :deep(.el-alert__description),.compact-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.chat-shell{height:calc(100vh - 154px);min-height:620px;display:grid;grid-template-columns:220px minmax(420px,1fr) 300px;overflow:hidden}.session-panel{display:flex;min-height:0;flex-direction:column;padding:16px 13px;border-right:1px solid #e8ebf1;background:#fafbfc;overflow:auto}.new-chat{width:100%;margin-bottom:13px}.session-search{height:34px;display:flex;align-items:center;gap:7px;padding:0 10px;border:1px solid #e1e5ed;border-radius:9px;background:white;color:#929caf}.session-search input{min-width:0;border:0;outline:0;background:transparent;font-size:9px}.session-label{margin:18px 8px 7px;color:#a0a8b8;font-size:8px;font-weight:750;letter-spacing:1px}.session-loading{min-height:90px}.session-empty{padding:18px 8px;color:#9aa3b5;text-align:center;font-size:9px}.compact-alert{margin:5px 0}.session-item{width:100%;display:flex;align-items:center;gap:8px;padding:10px;border:0;border-radius:10px;background:transparent;color:#7d879c;text-align:left;cursor:pointer}.session-item:hover,.session-item.active{background:#eef0ff;color:#5665df}.session-item>span{display:flex;min-width:0;flex:1;flex-direction:column}.session-item b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px}.session-item small{margin-top:4px;color:#a1a9b8;font-size:8px}.rag-scope{display:flex;flex-direction:column;margin-top:auto;padding:12px;border:1px solid #dfe8e6;border-radius:11px;background:#f4faf8}.rag-scope>span{display:flex;align-items:center;gap:6px;color:#188c76;font-size:8px;font-weight:750}.rag-scope>span i{width:6px;height:6px;border-radius:50%;background:#16a889}.rag-scope b{margin-top:7px;color:#536a67;font-size:8px}.rag-scope small{margin-top:5px;color:#91a29f;font-size:7px}.conversation{min-width:0;display:flex;min-height:0;flex-direction:column;background:#fff}.conversation-head{height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #ebedf2}.conversation-head>div{display:flex;align-items:center;gap:9px}.ai-avatar,.message-avatar{width:30px;height:30px;display:grid;place-items:center;flex:none;border-radius:10px;background:linear-gradient(145deg,#6575f0,#9b6ee8);color:white;font-size:12px}.conversation-head p{display:flex;flex-direction:column;margin:0}.conversation-head b{font-size:10px}.conversation-head small{display:flex;align-items:center;gap:5px;margin-top:4px;color:#929bad;font-size:8px}.conversation-head small i{width:5px;height:5px;border-radius:50%;background:#17aa8c}.model-pill{padding:5px 8px;border-radius:7px;background:#f0f2ff;color:#606fe4;font-size:8px;font-weight:700}.inner-alert{margin:12px 18px}.documents-loading{min-height:180px}.no-documents{display:grid;flex:1;place-items:center}.messages{flex:1;overflow:auto;padding:21px 22px}.message{display:flex;gap:11px;margin-bottom:23px}.message.user{flex-direction:row-reverse}.message.user .message-avatar{background:#eef0f5;color:#64708b}.message-block{max-width:86%}.user .message-block{display:flex;align-items:flex-end;flex-direction:column}.message-meta{display:flex;align-items:center;gap:7px;margin-bottom:7px}.message-meta b{font-size:9px}.message-meta span{color:#a1a8b7;font-size:8px}.message-meta em{padding:2px 6px;border-radius:5px;background:#fff2e5;color:#d57b27;font-size:7px;font-style:normal}.bubble{padding:12px 14px;border-radius:4px 13px 13px 13px;background:#f4f6fa;color:#49546d;font-size:10px;line-height:1.75;white-space:pre-wrap}.bubble p{margin:0 0 8px}.bubble p:last-child{margin-bottom:0}.user .bubble{border-radius:13px 4px 13px 13px;background:#5d6ceb;color:white}.answer-tools{display:flex;align-items:center;gap:12px;margin-top:8px}.answer-tools button{display:flex;align-items:center;gap:4px;padding:0;border:0;background:transparent;color:#6875dd;font-size:8px;cursor:pointer}.typing{display:flex;align-items:center;gap:4px;padding:13px;border-radius:4px 12px 12px;background:#f4f6fa}.typing i{width:5px;height:5px;border-radius:50%;background:#6b79e7;animation:bounce 1s infinite alternate}.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}.typing span{margin-left:6px;color:#8b95a9;font-size:8px}.pending-question{display:block;margin-top:6px;color:#929bad;font-size:8px}@keyframes bounce{to{transform:translateY(-4px)}}.composer-wrap{padding:8px 18px 12px}.scope-select{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:10px;margin-bottom:8px;color:#7d879c;font-size:8px}.suggestions{display:flex;gap:6px;overflow:auto;margin-bottom:8px}.suggestions button{white-space:nowrap;padding:6px 9px;border:1px solid #e0e4ee;border-radius:999px;background:#fff;color:#6f7990;font-size:8px;cursor:pointer}.suggestions button:hover{border-color:#9ca6ef;color:#5a69df}.suggestions button:disabled{opacity:.5}.composer{overflow:hidden;border:1px solid #d8ddea;border-radius:13px;background:#fff;box-shadow:0 8px 20px rgba(47,58,91,.07)}.composer textarea{width:100%;padding:11px 12px 3px;border:0;outline:0;resize:none;color:#424d67;font:10px/1.5 inherit}.composer textarea:disabled{background:#fafbfc}.composer>div{display:flex;align-items:center;justify-content:space-between;padding:4px 7px 7px 12px}.composer>div span{color:#9aa2b2;font-size:7px}.composer>div button{width:29px;height:29px;display:grid;place-items:center;border:0;border-radius:9px;background:var(--brand);color:white;cursor:pointer}.composer>div button:disabled{opacity:.4}.composer-wrap>p{text-align:center;margin:6px 0 0;color:#adb3c0;font-size:7px}.sources-panel{overflow:auto;padding:17px 14px;border-left:1px solid #e8ebf1;background:#fafbfc}.sources-head{display:flex;justify-content:space-between;align-items:flex-start}.sources-head h2{margin:0;font-size:12px}.sources-head p{margin:5px 0;color:#929bad;font-size:8px}.source-list{display:grid;gap:9px;margin-top:14px}.source-list article{padding:12px;border:1px solid #e3e7ef;border-radius:11px;background:white}.source-top{display:flex;justify-content:space-between}.source-top span{min-width:24px;height:20px;display:grid;place-items:center;padding:0 4px;border-radius:6px;background:#e9ecff;color:#5f6ee4;font-size:8px;font-weight:800}.source-top strong{color:#15a087;font-size:8px}.source-list h3{margin:9px 0 6px;color:#3f4a64;font-size:9px}.source-location{display:flex;align-items:center;gap:4px;margin:0;color:#7b86a0;font-size:7px}.source-list blockquote{margin:9px 0;padding:8px;border-left:2px solid #8490ed;background:#f7f8fc;color:#69748a;font-size:8px;line-height:1.6;white-space:pre-wrap}.source-list small{color:#9aa3b5;font-size:7px}@media(max-width:1200px){.chat-shell{grid-template-columns:190px 1fr}.sources-panel{display:none}}@media(max-width:760px){.chat-shell{height:auto;min-height:620px;grid-template-columns:1fr}.session-panel{max-height:260px;border-right:0;border-bottom:1px solid #e8ebf1}.messages{min-height:360px;padding:17px 13px}.message-block{max-width:92%}}
.chat-welcome{max-width:520px;margin:70px auto 0;padding:28px;text-align:center}.chat-welcome>span{width:46px;height:46px;display:grid;place-items:center;margin:auto;border-radius:14px;background:linear-gradient(145deg,#6575f0,#9b6ee8);color:#fff;font-weight:800}.chat-welcome h2{margin:16px 0 8px;color:#34415d;font-size:18px}.chat-welcome p{margin:0;color:#7f899d;font-size:12px;line-height:1.7}.runtime-status{display:flex!important;align-items:flex-end!important;flex-direction:column;gap:3px!important}.runtime-status>small{margin:0;color:#98a1b3;font-size:9px}.runtime-alert{margin:10px 18px 0}.runtime-alert :deep(.el-alert__content){width:100%}.runtime-alert :deep(.el-alert__description){display:flex;justify-content:flex-end;margin:0}.model-pill.demo{background:#fff3df;color:#b76a17}.model-pill.error{background:#fff0f0;color:#c74b4b}.ai-avatar.demo,.message-avatar.demo,.chat-welcome>span.demo{background:linear-gradient(145deg,#e7a13b,#cc7134);font-size:8px;letter-spacing:-.3px}.conversation-head small i.warning{background:#e39a32}.message-meta em.enough{background:#eaf8f4;color:#148b75}.session-search input,.session-item b,.conversation-head b,.message-meta b{font-size:11px}.session-label,.session-item small,.conversation-head small,.rag-scope>span,.rag-scope b,.model-pill,.message-meta span,.message-meta em,.answer-tools button,.typing span,.pending-question,.scope-select,.suggestions button,.composer>div span,.composer-wrap>p,.sources-head p,.source-top span,.source-top strong,.source-location,.source-list small{font-size:10px}.rag-scope small{font-size:9px}.bubble,.composer textarea{font-size:12px}.sources-head h2{font-size:14px}.source-list h3{font-size:12px}.source-list blockquote{font-size:11px}
@media(max-width:760px){
  .sources-panel{display:block;max-height:360px;border-top:1px solid #e8ebf1;border-left:0}
}
</style>
