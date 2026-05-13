<template>
  <article class="repo-card animate-fade-in-up" @click="handleCardClick">
    <!-- 翻译按钮（没有中文摘要时显示，绝对定位不参与卡片点击） -->
    <div v-if="!repo.summary_zh && !repo.name_zh && store.lang === 'zh' && !isDescChinese"
         class="translate-overlay"
         @click.stop>
      <button class="translate-btn" :class="{ loading: translating }"
        @click.stop.prevent="doTranslate('auto')">
        <span v-if="translating">翻译中...</span>
        <span v-else>🌐 翻译</span>
      </button>
      <button class="translate-btn-sm" @click.stop.prevent="doTranslate('google')"
        :disabled="translating" title="Google 免费翻译">G</button>
      <button v-if="hasDeepSeek" class="translate-btn-sm accent"
        @click.stop.prevent="doTranslate('deepseek')"
        :disabled="translating" title="DeepSeek 高质量翻译">D</button>
    </div>
    <!-- 头部 -->
    <div class="card-header">
      <div class="repo-meta">
        <span class="repo-owner mono">{{ repo.owner }}</span>
        <span class="separator">/</span>
        <span class="repo-name">{{ displayName }}</span>
        <span v-if="repo.has_chinese_readme" class="cn-badge" title="有中文文档">中</span>
      </div>
      <div class="card-actions">
        <a :href="repo.html_url" target="_blank" rel="noopener"
           class="github-link" @click.stop>
          <GithubIcon :size="14" />
        </a>
      </div>
    </div>

    <!-- 描述 -->
    <p class="repo-desc">{{ displayDesc }}</p>

    <!-- 标签：优先 tags_zh，其次 topics，最后用 sub_categories 兜底 -->
    <div class="repo-tags">
      <span v-for="tag in displayTags" :key="tag" class="tag">{{ tag }}</span>
    </div>

    <!-- 底部统计 -->
    <div class="card-footer">
      <div class="footer-left">
        <!-- 语言 -->
        <span v-if="repo.language" class="lang-badge">
          <span class="lang-dot" :style="{ background: getLangColor(repo.language) }"></span>
          <span class="mono">{{ repo.language }}</span>
        </span>
        <!-- AI 评分 -->
        <span class="ai-score" :class="getScoreClass(repo.ai_score)">
          <ZapIcon :size="10" />
          <span class="mono">{{ (repo.ai_score * 100).toFixed(0) }}</span>
        </span>
      </div>

      <div class="footer-right">
        <!-- 今日新增 -->
        <div v-if="repo.stars_today > 0" class="stat-item hot">
          <TrendingUpIcon :size="11" />
          <span class="mono">+{{ formatNum(repo.stars_today) }}</span>
        </div>
        <!-- 总星数 -->
        <div class="stat-item">
          <StarIcon :size="11" />
          <span class="mono">{{ formatNum(repo.stars_total) }}</span>
        </div>
        <!-- Fork -->
        <div v-if="repo.forks_total > 0" class="stat-item">
          <GitForkIcon :size="11" />
          <span class="mono">{{ formatNum(repo.forks_total) }}</span>
        </div>
      </div>
    </div>

    <!-- 排名标记 -->
    <div v-if="repo.rank > 0 && repo.rank <= 10" class="rank-badge mono">
      #{{ repo.rank }}
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { StarIcon, TrendingUpIcon, ZapIcon, GitForkIcon } from 'lucide-vue-next'
import type { Repo } from '@/api'
import { api } from '@/api'
import { useAppStore } from '@/stores/app'

const GithubIcon = {
  props: ['size'],
  template: `<svg :width="size||14" :height="size||14" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
  </svg>`
}

const CAT_NAMES: Record<string, string> = {
  llm: '大语言模型', rag: 'RAG检索', agent: 'AI Agent',
  mcp: 'MCP协议', vision: '图像视觉', audio: '语音音频',
  training: '模型训练', inference: '模型推理', toolchain: 'AI工具链',
  dataset: '数据集', safety: 'AI安全', robotics: '具身智能',
  codegen: '代码生成', other: '其他AI',
}

const props = defineProps<{ repo: Repo }>()
const emit = defineEmits<{ click: [repo: Repo] }>()
const store = useAppStore()
const translating = ref(false)
const isTranslateAction = ref(false)

// 从 store 读取，全局只查一次
const hasDeepSeek = computed(() => store.hasDeepSeek)

// 描述是否已经是中文（中文字符占比 > 20%）
const isDescChinese = computed(() => {
  const text = props.repo.description || ''
  if (!text) return false
  const cjk = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length
  return cjk / text.length >= 0.2
})

function handleCardClick(e: MouseEvent) {
  // 如果点击的是按钮或翻译区域，不触发详情
  const target = e.target as HTMLElement
  if (target.closest('.translate-bar') || target.closest('button') || target.closest('a')) return
  emit('click', props.repo)
}

async function doTranslate(engine: 'auto' | 'deepseek' | 'google') {
  if (translating.value) return
  translating.value = true
  try {
    const res = await api.translateRepo(props.repo.full_name, engine)
    const data = res.data as any
    if (data.success) {
      props.repo.summary_zh = data.summary_zh || props.repo.summary_zh
      if (data.name_zh) props.repo.name_zh = data.name_zh
      if (data.tags_zh) props.repo.tags_zh = data.tags_zh
    }
  } catch (e) {
    console.error('Translation failed:', e)
  } finally {
    translating.value = false
    setTimeout(() => { isTranslateAction.value = false }, 100)
  }
}

// 根据语言显示名称和描述
const displayName = computed(() =>
  store.lang === 'zh' && props.repo.name_zh ? props.repo.name_zh : props.repo.repo_name
)
const displayDesc = computed(() =>
  store.lang === 'zh' && props.repo.summary_zh
    ? props.repo.summary_zh
    : props.repo.description || '暂无描述'
)

// 标签优先级：tags_zh > topics > 主分类名兜底（ai_score 足够高才兜底）
const displayTags = computed(() => {
  if (props.repo.tags_zh?.length) return props.repo.tags_zh.slice(0, 4)
  if (props.repo.topics?.length) return props.repo.topics.slice(0, 4)
  // ai_score 低于 0.4 说明分类可信度不高，不显示兜底标签避免误导
  if ((props.repo.ai_score ?? 0) < 0.4) return []
  const mainCat = (props.repo.sub_categories || [])[0]
  return mainCat ? [CAT_NAMES[mainCat] || mainCat] : []
})

function formatNum(n: number | null | undefined) {
  const num = n ?? 0
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toString()
}

function getLangColor(lang: string): string {
  const colors: Record<string, string> = {
    Python: '#3572A5', TypeScript: '#2b7489', JavaScript: '#f1e05a',
    Rust: '#dea584', Go: '#00ADD8', Java: '#b07219', 'C++': '#f34b7d',
    'Jupyter Notebook': '#DA5B0B', Swift: '#ffac45', Kotlin: '#A97BFF',
    'C#': '#178600', Ruby: '#701516', PHP: '#4F5D95',
  }
  return colors[lang] || '#8888a8'
}

function getScoreClass(score: number) {
  if (score >= 0.8) return 'score-high'
  if (score >= 0.5) return 'score-mid'
  return 'score-low'
}
</script>

<style scoped>
.repo-card {
  position: relative;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  overflow: hidden;
}
.repo-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--accent-glow) 0%, transparent 60%);
  opacity: 0;
  transition: opacity 0.2s;
}
.repo-card:hover {
  border-color: rgba(79, 70, 229, 0.35);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
}
.repo-card:hover::before { opacity: 1; }

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.repo-meta {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}
.repo-owner {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.separator {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 1px;
}
.repo-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cn-badge {
  font-size: 9px;
  font-weight: 700;
  color: var(--cyan);
  border: 1px solid var(--cyan);
  border-radius: 3px;
  padding: 0 3px;
  line-height: 1.4;
  opacity: 0.8;
}
.github-link {
  color: var(--text-muted);
  display: flex;
  align-items: center;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.github-link:hover { color: var(--text-primary); background: var(--bg-hover); }

.repo-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-weight: 400;
}

.translate-overlay {
  position: absolute;
  top: 8px;
  right: 36px;  /* 避开右上角的 GitHub 链接按钮 */
  display: flex;
  align-items: center;
  gap: 3px;
  z-index: 10;
  opacity: 0;
  transition: opacity 0.15s;
}
.repo-card:hover .translate-overlay { opacity: 1; }
.translate-btn {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.translate-btn:hover { border-color: var(--accent); color: var(--accent); }
.translate-btn.loading { opacity: 0.6; cursor: not-allowed; }
.translate-btn-sm {
  font-size: 10px; font-weight: 700;
  width: 20px; height: 20px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  display: flex; align-items: center; justify-content: center;
}
.translate-btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.translate-btn-sm.accent { border-color: rgba(79,70,229,0.3); color: var(--accent); background: var(--accent-glow); }
.translate-btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }

.repo-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.tag {
  font-size: 10px;
  color: var(--text-secondary);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 6px;
  font-weight: 500;
  transition: all 0.15s;
}
.repo-card:hover .tag {
  border-color: rgba(99,102,241,0.2);
  color: var(--text-secondary);
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.footer-left, .footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lang-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.lang-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ai-score {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}
.score-high { color: var(--green); background: rgba(34,197,94,0.1); }
.score-mid  { color: var(--amber); background: rgba(245,158,11,0.1); }
.score-low  { color: var(--text-muted); background: var(--bg-elevated); }

.stat-item {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
}
.stat-item.hot { color: var(--amber); font-weight: 600; }

.rank-badge {
  position: absolute;
  top: 10px;
  right: 36px;
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-glow);
  border: 1px solid rgba(99,102,241,0.3);
  border-radius: 3px;
  padding: 1px 5px;
}
</style>
