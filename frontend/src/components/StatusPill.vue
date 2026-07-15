<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = { queued: '排队中', uploaded: '已上传', parsing: '解析中', embedding: '向量化中', ready: '已就绪', processing: '处理中', running: '处理中', retrying: '重试中', success: '已完成', succeeded: '已完成', completed: '已完成', failed: '失败', cancelled: '已取消', todo: '待开始', doing: '进行中', done: '已完成' }
</script>

<template><span class="status-pill" :class="`is-${status}`"><i></i>{{ labels[status] || status }}</span></template>

<style scoped>
.status-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;background:#f2f4f8;color:#65708a;font-size:11px;font-weight:650;white-space:nowrap}.status-pill i{width:6px;height:6px;border-radius:50%;background:currentColor}.is-processing,.is-running,.is-parsing,.is-embedding,.is-doing{background:#edf0ff;color:#5364e8}.is-success,.is-succeeded,.is-completed,.is-ready,.is-done{background:#e9f8f3;color:#159878}.is-retrying{background:#fff4e8;color:#df852d}.is-failed,.is-cancelled{background:#ffeded;color:#dc5f5f}.is-queued,.is-uploaded,.is-todo{background:#f1f3f7;color:#7a849c}
</style>
