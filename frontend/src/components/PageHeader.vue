<script setup lang="ts">
withDefaults(defineProps<{ title: string; eyebrow?: string; description?: string }>(), { eyebrow: '', description: '' })
</script>

<template>
  <header class="page-heading">
    <div>
      <span v-if="eyebrow" class="eyebrow">{{ eyebrow }}</span>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div class="page-heading__actions"><slot /></div>
  </header>
</template>

<style scoped>
.page-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:32px; margin-bottom:28px; }
.page-heading>div:first-child { min-width:0; }
.eyebrow { display:flex; align-items:center; gap:8px; margin-bottom:11px; color:var(--brand); font-size:10px; line-height:1; letter-spacing:2.4px; font-weight:850; }
.eyebrow::before { content:""; width:24px; height:2px; border-radius:2px; background:linear-gradient(90deg,var(--brand),var(--teal)); }
h1 { margin:0; color:var(--ink); font-size:34px; line-height:1.15; letter-spacing:-1.15px; font-weight:800; }
p { max-width:760px; margin:9px 0 0; color:var(--muted); font-size:13px; line-height:1.65; }
.page-heading__actions { display:flex; align-items:center; gap:10px; flex:none; }
@media (max-width:700px) { .page-heading{align-items:flex-start;flex-direction:column;gap:18px;margin-bottom:24px}.page-heading__actions{width:100%;flex-wrap:wrap}h1{font-size:26px}p{font-size:13px} }
</style>
