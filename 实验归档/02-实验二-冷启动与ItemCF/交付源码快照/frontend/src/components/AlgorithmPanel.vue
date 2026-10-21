<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import type { AlgorithmResult } from '../types'
const props = withDefaults(defineProps<{ endpoint: string | null; label: string; emptySubject?: string }>(), { emptySubject: '登录后体验' })
const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null)
const strategy = computed(() => {
  const sources = new Set(result.value?.items.flatMap(item => item.recall_sources || []) || [])
  if (sources.has('genre_preference')) return '冷启动个性化：按你选择的电影类型筛选，再用历史口碑排序。'
  if (sources.has('itemcf')) return '个性化 ItemCF：根据真实用户的正向评分与收藏种子计算相似电影；收藏按独立二元信号处理。'
  if (sources.has('popular_non_personalized')) return '非个性化兜底：当前没有可用偏好，结果按历史评分热度排序，不代表个人兴趣。'
  if (sources.has('popular_fallback')) return '部分结果来自热门兜底：当协同过滤邻居不足时补足列表，并已明确标注来源。'
  if (result.value?.algorithm === 'popular') return '热门榜单：按历史评分数量与均分的平滑口碑排序，不使用个人画像。'
  return result.value?.algorithm === 'content' ? '内容推荐：根据高分历史电影的类型相似度排序。' : ''
})
let run = 0
onScopeDispose(() => { run++ })
async function load() {
  const seq = ++run
  error.value = null; result.value = null; unavailable.value = false; loading.value = false
  if (!props.endpoint) return
  loading.value = true
  try { const response = await http.get<AlgorithmResult>(props.endpoint); if (seq === run) result.value = response.data }
  catch (e) {
    if (seq !== run) return
    if (e instanceof ApiError && e.status === 501 && e.code === 'ALGORITHM_NOT_IMPLEMENTED') unavailable.value = true
    else error.value = e
  } finally { if (seq === run) loading.value = false }
}
watch(() => props.endpoint, load, { immediate: true })
</script>
<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top"><h3>{{ label }}</h3><span class="small-label">RECOMMENDATION</span></div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div><span class="status-pill">{{ !endpoint ? emptySubject : '尚未实现' }}</span><h3>{{ !endpoint ? '选择观众，开始探索' : '下一部好电影，等待算法发现' }}</h3><p>{{ !endpoint ? '先选择历史用户或登录注册账号。推荐功能等待算法接入。' : '等待算法接入；当前没有模型版本或推荐结果。' }}</p></div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>
      <div v-else-if="result" class="recommendation-results"><p>模型版本 {{ result.model_version }} · {{ result.dataset_version }}</p><p v-if="strategy" class="strategy-note">{{ strategy }}</p><p v-if="!result.items.length">本次没有推荐结果。</p><ol v-else><li v-for="item in result.items" :key="item.movie_id"><RouterLink :to="`/movies/${item.movie_id}`">电影 #{{ item.movie_id }}</RouterLink> · 排名 {{ item.rank }}<span v-if="item.score !== null"> · 模型分数 {{ item.score }}</span><span v-if="item.recall_sources?.length"> · 来源 {{ item.recall_sources.join(' + ') }}</span></li></ol></div>
    </StatePanel>
  </section>
</template>

<style scoped>
.strategy-note { margin: 12px 0; padding: 10px 12px; border-left: 2px solid var(--accent); background: var(--surface-soft); color: var(--muted); line-height: 1.7; }
</style>
