<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, CirclePlus, Clock, Document, Promotion, Search, Star, User } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { learningApi } from '@/api/services'
import type { Citation } from '@/types'

type Message = { role: 'user' | 'assistant'; content: string; time: string; citations?: Citation[]; cached?: boolean }
const question = ref('')
const sending = ref(false)
const messageArea = ref<HTMLElement>()
const activeSession = ref(1)
const sessions = [
  { id: 1, title: '什么是第三范式？', time: '10:32' },
  { id: 2, title: '候选码应该如何判断', time: '昨天' },
  { id: 3, title: '事务隔离级别对比', time: '周一' },
  { id: 4, title: 'B+ 树为什么适合索引', time: '07-10' },
]
const messages = ref<Message[]>([
  { role: 'user', content: '什么是第三范式？能用一个简单的例子解释吗？', time: '10:32' },
  { role: 'assistant', time: '10:32', content: '第三范式（3NF）要求关系已经满足第二范式，并且每个非主属性都不传递依赖于候选码。[1]\n\n举个例子：学生选课表（学号，课程号，教师编号，教师姓名），主键是（学号，课程号）。其中“教师姓名”依赖“教师编号”，而“教师编号”又由课程号决定，这就形成了传递依赖。把教师信息拆成单独的教师表后，就满足了第三范式。[2]\n\n判断时可以记住三个步骤：先找候选码 → 区分主属性 → 检查是否存在非主属性对码的传递依赖。[3]', citations: [
    { id: 1, document: '数据库系统概论（第6版）.pdf', page: 176, chapter: '第6章 关系数据理论', snippet: '若关系模式 R∈2NF，且每一个非主属性都不传递依赖于候选码，则 R∈3NF。', score: 0.94 },
    { id: 2, document: '数据库课程讲义-范式.pptx', page: 24, chapter: '规范化理论', snippet: '第三范式用于消除非主属性对码的传递函数依赖。', score: 0.89 },
    { id: 3, document: '期末复习重点.md', page: 3, chapter: '高频考点', snippet: '判断 3NF：先找候选码，再找主属性，最后检查函数依赖。', score: 0.82 },
  ], cached: false },
])
const activeCitations = ref<Citation[]>(messages.value[1].citations || [])
const suggestions = ['3NF 和 BCNF 有什么区别？', '给我出一道范式判断题', '如何快速找到候选码？']

async function send(text = question.value) {
  const value = text.trim()
  if (!value || sending.value) return
  messages.value.push({ role: 'user', content: value, time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) })
  question.value = ''
  sending.value = true
  await nextTick(); messageArea.value?.scrollTo({ top: messageArea.value.scrollHeight, behavior: 'smooth' })
  try {
    const result = await learningApi.ask(value)
    messages.value.push({ role: 'assistant', content: result.answer + '\n\n你可以继续问我它和 BCNF 的区别，或者让我基于这部分资料出一道练习题。', time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }), citations: result.citations, cached: result.cached })
    activeCitations.value = result.citations
  } catch { ElMessage.error('问答服务暂时不可用，请稍后重试') }
  finally { sending.value = false; await nextTick(); messageArea.value?.scrollTo({ top: messageArea.value.scrollHeight, behavior: 'smooth' }) }
}

function showSources(message: Message) { if (message.citations) activeCitations.value = message.citations }
</script>

<template>
  <div class="chat-page">
    <PageHeader title="智能问答" eyebrow="RAG ASSISTANT" description="答案严格依据你的课程资料生成，并标注可核验的页码与章节。">
      <el-select model-value="数据库系统" style="width:180px"><el-option label="数据库系统" value="数据库系统" /></el-select>
    </PageHeader>
    <section class="chat-shell content-card">
      <aside class="session-panel">
        <el-button type="primary" class="new-chat"><el-icon><CirclePlus /></el-icon>新建对话</el-button>
        <div class="session-search"><el-icon><Search /></el-icon><input placeholder="搜索历史对话" /></div>
        <span class="session-label">最近对话</span>
        <button v-for="item in sessions" :key="item.id" class="session-item" :class="{ active: activeSession === item.id }" @click="activeSession = item.id"><el-icon><ChatDotRound /></el-icon><span><b>{{ item.title }}</b><small>{{ item.time }}</small></span></button>
        <div class="rag-scope"><span><i></i>知识库已就绪</span><b>12 份资料 · 2,438 个文本块</b><small>仅检索当前课程有效版本</small></div>
      </aside>

      <main class="conversation">
        <div class="conversation-head"><div><span class="ai-avatar">✦</span><p><b>StudyPilot AI</b><small><i></i>基于数据库系统知识库</small></p></div><span class="model-pill">RAG · DeepSeek</span></div>
        <div ref="messageArea" class="messages">
          <div v-for="(message,index) in messages" :key="index" class="message" :class="message.role">
            <span class="message-avatar"><el-icon v-if="message.role === 'user'"><User /></el-icon><template v-else>✦</template></span>
            <div class="message-block">
              <div class="message-meta"><b>{{ message.role === 'user' ? '你' : 'StudyPilot AI' }}</b><span>{{ message.time }}</span><em v-if="message.cached">Redis 缓存命中</em></div>
              <div class="bubble"><p v-for="paragraph in message.content.split('\n\n')" :key="paragraph">{{ paragraph }}</p></div>
              <div v-if="message.citations" class="answer-tools"><button @click="showSources(message)"><el-icon><Document /></el-icon>{{ message.citations.length }} 条引用来源</button><button><el-icon><Star /></el-icon>收藏答案</button><span>检索耗时 186ms · 置信度 91%</span></div>
            </div>
          </div>
          <div v-if="sending" class="message assistant"><span class="message-avatar">✦</span><div class="message-block"><div class="message-meta"><b>StudyPilot AI</b><span>正在检索资料</span></div><div class="typing"><i></i><i></i><i></i><span>查询 pgvector 并重排序…</span></div></div></div>
        </div>
        <div class="composer-wrap">
          <div class="suggestions"><button v-for="item in suggestions" :key="item" @click="send(item)">{{ item }}</button></div>
          <div class="composer"><textarea v-model="question" rows="2" placeholder="向课程资料提问，Shift + Enter 换行…" @keydown.enter.exact.prevent="send()"></textarea><div><span>检索范围：全部 12 份资料</span><button :disabled="sending || !question.trim()" aria-label="发送问题" @click="send()"><el-icon><Promotion /></el-icon></button></div></div>
          <p>AI 可能出错，请通过右侧引用核验关键信息</p>
        </div>
      </main>

      <aside class="sources-panel">
        <div class="sources-head"><div><h2>引用来源</h2><p>{{ activeCitations.length }} 条内容支持当前答案</p></div><span>Top-K 5</span></div>
        <div class="source-list"><article v-for="source in activeCitations" :key="source.id"><div class="source-top"><span>{{ source.id }}</span><strong>{{ Math.round(source.score * 100) }}% 匹配</strong></div><h3>{{ source.document }}</h3><p class="source-location"><el-icon><Document /></el-icon>第 {{ source.page }} 页 · {{ source.chapter }}</p><blockquote>“{{ source.snippet }}”</blockquote><button>打开原文并定位 →</button></article></div>
        <div class="retrieval-info"><h3>本次检索链路</h3><p><span>缓存</span><b>未命中</b><i>12ms</i></p><p><span>向量检索</span><b>pgvector</b><i>78ms</i></p><p><span>重排序</span><b>Top 3</b><i>96ms</i></p><p><span>文档版本</span><b>仅当前有效</b><i>✓</i></p></div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.chat-shell{height:calc(100vh - 154px);min-height:620px;display:grid;grid-template-columns:205px minmax(420px,1fr) 285px;overflow:hidden}.session-panel{display:flex;flex-direction:column;padding:16px 13px;border-right:1px solid #e8ebf1;background:#fafbfc}.new-chat{width:100%;margin-bottom:13px}.session-search{height:34px;display:flex;align-items:center;gap:7px;padding:0 10px;border:1px solid #e1e5ed;border-radius:9px;background:white;color:#929caf}.session-search input{min-width:0;border:0;outline:0;background:transparent;font-size:9px}.session-label{margin:18px 8px 7px;color:#a0a8b8;font-size:8px;font-weight:750;letter-spacing:1px}.session-item{width:100%;display:flex;align-items:center;gap:8px;padding:10px;border:0;border-radius:10px;background:transparent;color:#7d879c;text-align:left;cursor:pointer}.session-item:hover,.session-item.active{background:#eef0ff;color:#5665df}.session-item>span{display:flex;min-width:0;flex:1;flex-direction:column}.session-item b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px}.session-item small{margin-top:4px;color:#a1a9b8;font-size:8px}.rag-scope{display:flex;flex-direction:column;margin-top:auto;padding:12px;border:1px solid #dfe8e6;border-radius:11px;background:#f4faf8}.rag-scope>span{display:flex;align-items:center;gap:6px;color:#188c76;font-size:8px;font-weight:750}.rag-scope>span i{width:6px;height:6px;border-radius:50%;background:#16a889}.rag-scope b{margin-top:7px;color:#536a67;font-size:8px}.rag-scope small{margin-top:5px;color:#91a29f;font-size:7px}.conversation{min-width:0;display:flex;flex-direction:column;background:#fff}.conversation-head{height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #ebedf2}.conversation-head>div{display:flex;align-items:center;gap:9px}.ai-avatar,.message-avatar{width:30px;height:30px;display:grid;place-items:center;flex:none;border-radius:10px;background:linear-gradient(145deg,#6575f0,#9b6ee8);color:white;font-size:12px}.conversation-head p{display:flex;flex-direction:column;margin:0}.conversation-head b{font-size:10px}.conversation-head small{display:flex;align-items:center;gap:5px;margin-top:4px;color:#929bad;font-size:8px}.conversation-head small i{width:5px;height:5px;border-radius:50%;background:#17aa8c}.model-pill{padding:5px 8px;border-radius:7px;background:#f0f2ff;color:#606fe4;font-size:8px;font-weight:700}.messages{flex:1;overflow:auto;padding:21px 22px}.message{display:flex;gap:11px;margin-bottom:23px}.message.user{flex-direction:row-reverse}.message.user .message-avatar{background:#eef0f5;color:#64708b}.message-block{max-width:86%}.user .message-block{display:flex;align-items:flex-end;flex-direction:column}.message-meta{display:flex;align-items:center;gap:7px;margin-bottom:7px}.message-meta b{font-size:9px}.message-meta span{color:#a1a8b7;font-size:8px}.message-meta em{padding:2px 6px;border-radius:5px;background:#eaf8f4;color:#188f78;font-size:7px;font-style:normal}.bubble{padding:12px 14px;border-radius:4px 13px 13px 13px;background:#f4f6fa;color:#49546d;font-size:10px;line-height:1.75}.bubble p{margin:0 0 8px}.bubble p:last-child{margin-bottom:0}.user .bubble{border-radius:13px 4px 13px 13px;background:#5d6ceb;color:white}.answer-tools{display:flex;align-items:center;gap:12px;margin-top:8px}.answer-tools button{display:flex;align-items:center;gap:4px;padding:0;border:0;background:transparent;color:#6875dd;font-size:8px;cursor:pointer}.answer-tools span{margin-left:auto;color:#a0a8b7;font-size:7px}.typing{display:flex;align-items:center;gap:4px;padding:13px;border-radius:4px 12px 12px;background:#f4f6fa}.typing i{width:5px;height:5px;border-radius:50%;background:#6b79e7;animation:bounce 1s infinite alternate}.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}.typing span{margin-left:6px;color:#8b95a9;font-size:8px}@keyframes bounce{to{transform:translateY(-4px)}}.composer-wrap{padding:8px 18px 12px}.suggestions{display:flex;gap:6px;overflow:auto;margin-bottom:8px}.suggestions button{white-space:nowrap;padding:6px 9px;border:1px solid #e0e4ee;border-radius:999px;background:#fff;color:#6f7990;font-size:8px;cursor:pointer}.suggestions button:hover{border-color:#9ca6ef;color:#5a69df}.composer{overflow:hidden;border:1px solid #d8ddea;border-radius:13px;background:#fff;box-shadow:0 8px 20px rgba(47,58,91,.07)}.composer textarea{width:100%;padding:11px 12px 3px;border:0;outline:0;resize:none;color:#424d67;font:10px/1.5 inherit}.composer>div{display:flex;align-items:center;justify-content:space-between;padding:4px 7px 7px 12px}.composer>div span{color:#9aa2b2;font-size:7px}.composer>div button{width:29px;height:29px;display:grid;place-items:center;border:0;border-radius:9px;background:var(--brand);color:white;cursor:pointer}.composer>div button:disabled{opacity:.4}.composer-wrap>p{text-align:center;margin:6px 0 0;color:#adb3c0;font-size:7px}.sources-panel{overflow:auto;padding:17px 14px;border-left:1px solid #e8ebf1;background:#fafbfc}.sources-head{display:flex;justify-content:space-between;align-items:flex-start}.sources-head h2{margin:0;font-size:12px}.sources-head p{margin:5px 0;color:#929bad;font-size:8px}.sources-head>span{padding:4px 6px;border-radius:6px;background:#eef0ff;color:#6070e3;font-size:7px}.source-list{display:grid;gap:9px;margin-top:14px}.source-list article{padding:12px;border:1px solid #e3e7ef;border-radius:11px;background:white}.source-top{display:flex;justify-content:space-between}.source-top span{width:18px;height:18px;display:grid;place-items:center;border-radius:6px;background:#e9ecff;color:#5f6ee4;font-size:8px;font-weight:800}.source-top strong{color:#15a087;font-size:8px}.source-list h3{margin:9px 0 6px;color:#3f4a64;font-size:9px}.source-location{display:flex;align-items:center;gap:4px;margin:0;color:#7b86a0;font-size:7px}.source-list blockquote{margin:9px 0;padding:8px;border-left:2px solid #8490ed;background:#f7f8fc;color:#69748a;font-size:8px;line-height:1.6}.source-list button{padding:0;border:0;background:transparent;color:#6070df;font-size:8px;cursor:pointer}.retrieval-info{margin-top:14px;padding:12px;border-radius:11px;background:#eef1f7}.retrieval-info h3{margin:0 0 9px;font-size:9px}.retrieval-info p{display:flex;margin:6px 0;color:#8490a5;font-size:7px}.retrieval-info b{margin-left:auto;color:#59647c}.retrieval-info i{width:38px;text-align:right;font-style:normal;color:#98a1b1}@media(max-width:1200px){.chat-shell{grid-template-columns:180px 1fr}.sources-panel{display:none}}@media(max-width:760px){.chat-shell{height:calc(100vh - 145px);grid-template-columns:1fr}.session-panel{display:none}.messages{padding:17px 13px}.message-block{max-width:92%}.answer-tools span{display:none}}
</style>
