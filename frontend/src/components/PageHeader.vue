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
.page-heading { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; margin-bottom:24px; }
.eyebrow { display:block; color:var(--brand); font-size:10px; line-height:1; letter-spacing:2.5px; font-weight:800; margin-bottom:9px; }
h1 { margin:0; color:var(--ink); font-size:28px; line-height:1.18; letter-spacing:-.8px; font-weight:750; }
p { margin:9px 0 0; color:var(--muted); font-size:13px; }
.page-heading__actions { display:flex; align-items:center; gap:10px; }
@media (max-width:700px) { .page-heading{align-items:flex-start;flex-direction:column}.page-heading__actions{width:100%}h1{font-size:24px} }
</style>
