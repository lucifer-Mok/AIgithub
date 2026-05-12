<template>
  <Teleport to="body">
    <div class="drawer-overlay" @click.self="$emit('close')">
      <div class="drawer" :class="{ open: visible }">
        <!-- 关闭按钮 -->
        <button class="close-btn" @click="$emit('close')">
          <XIcon :size="16" />
        </button>

        <!-- 加载中 -->
        <div v-if="loading" class="drawer-loading">
          <div class="loading-dots">
            <span></span><span></span><span></span>
          </div>
        </div>

        <template v-else-if="repo">
          <!-- 头部 -->
          <div class="drawer-header">
            <div class="drawer-repo-name">
              <span class="mono muted">{{ repo.owner }}/</span>
              <span class="name">{{ displayName }}</span>
              <span v-if="repo.has_chinese_readme" class="cn-badge">中</span>
            </div>
            <div class="drawer-actions">
              <a :href="repo.html_url" target="_blank" rel="noopener" class="action-btn primary">
                <GithubIcon />
                GitHub
                <ExternalLinkIcon :size="11" />
              </a>
              <a v-if="repo.homepage" :href="repo.homepage" target="_blank" rel="noopener" class="action-btn">
                <GlobeIcon :size="13" />
                官网
              </a>
            </div>
          </div>

          <!-- 分类 & 标签 -->
          <div class="drawer-tags">
            <span v-if="repo.category" class="cat-tag">
              {{ repo.category.icon }} {{ repo.category.name }}
            </span>
            <span v-for="tag in (repo.tags_zh?.length ? repo.tags_zh : repo.topics).slice(0, 6)"
                  :key="tag" class="topic-tag">
              {{ tag }}
            </span>
          </div>

          <!-- 统计数据 -->
          <div class="stats-row">
            <div class="stat-box">
              <StarIcon :size="14" class="stat-icon amber" />
              <div>
                <div class="stat-num mono">{{ formatNum(repo.stars_total ?? 0) }}</div>
                <div class="stat-label">总 Stars</div>
              </div>
            </div>
            <div class="stat-box">
              <TrendingUpIcon :size="14" class="stat-icon green" />
              <div>
                <div class="stat-num mono">+{{ formatNum(repo.stars_today ?? 0) }}</div>
                <div class="stat-label">今日新增</div>
              </div>
            </div>
            <div class="stat-box">
              <GitForkIcon :size="14" class="stat-icon" />
              <div>
                <div class="stat-num mono">{{ formatNum(repo.forks_total ?? 0) }}</div>
                <div class="stat-label">Forks</div>
              </div>
            </div>
            <div class="stat-box">
              <ZapIcon :size="14" class="stat-icon accent" />
              <div>
                <div class="stat-num mono">{{ ((repo.ai_score ?? 0) * 100).toFixed(0) }}%</div>
                <div class="stat-label">AI 相关度</div>
              </div>
            </div>
          </div>

          <!-- 描述 -->
          <div class="drawer-section">
            <div class="section-title">项目介绍</div>
            <p class="desc-text">{{ displayDesc }}</p>
            <p v-if="store.lang === 'zh' && repo.summary_zh && repo.description" class="desc-original">
              {{ repo.description }}
            </p>
          </div>

          <!-- 趋势图 -->
          <div v-if="repo.trend?.length" class="drawer-section">
            <div class="section-title">近期趋势</div>
            <div class="trend-chart">
              <div class="chart-bars">
                <div
                  v-for="point in trendData"
                  :key="point.date"
                  class="chart-bar-wrap"
                  :title="`${point.date}: +${point.stars_today}`"
                >
                  <div
                    class="chart-bar"
                    :style="{ height: point.height + '%' }"
                    :class="{ highlight: point.stars_today === maxStars }"
                  ></div>
                </div>
              </div>
              <div class="chart-labels">
                <span class="mono">{{ trendData[0]?.date }}</span>
                <span class="mono">{{ trendData[trendData.length - 1]?.date }}</span>
              </div>
            </div>
          </div>

          <!-- 语言 -->
          <div v-if="repo.language" class="drawer-section">
            <div class="section-title">主要语言</div>
            <span class="lang-pill">
              <span class="lang-dot" :style="{ background: getLangColor(repo.language) }"></span>
              {{ repo.language }}
            </span>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  XIcon, StarIcon, TrendingUpIcon, GitForkIcon, ZapIcon,
  ExternalLinkIcon, GlobeIcon
} from 'lucide-vue-next'
import { api, type RepoDetail } from '@/api'
import { useAppStore } from '@/stores/app'

const GithubIcon = {
  template: `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
  </svg>`
}

const props = defineProps<{ repoName: string }>()
defineEmits<{ close: [] }>()

const store = useAppStore()
const repo = ref<RepoDetail | null>(null)

const displayName = computed(() =>
  store.lang === 'zh' && repo.value?.name_zh ? repo.value.name_zh : repo.value?.repo_name ?? ''
)
const displayDesc = computed(() =>
  store.lang === 'zh' && repo.value?.summary_zh
    ? repo.value.summary_zh
    : repo.value?.description ?? '暂无描述'
)
const loading = ref(true)
const visible = ref(false)

const maxStars = computed(() =>
  Math.max(...(repo.value?.trend?.map(t => t.stars_today) ?? [1]))
)

const trendData = computed(() =>
  (repo.value?.trend ?? []).slice(-30).map(t => ({
    ...t,
    height: maxStars.value > 0 ? Math.max(4, (t.stars_today / maxStars.value) * 100) : 4,
  }))
)

watch(() => props.repoName, async (name) => {
  if (!name) return
  loading.value = true
  visible.value = false
  try {
    const res = await api.getRepo(name)
    repo.value = res.data
    setTimeout(() => { visible.value = true }, 50)
  } finally {
    loading.value = false
  }
}, { immediate: true })

function formatNum(n: number | null | undefined) {
  const num = n ?? 0
  if (num >= 1000) return (num / 1000).toFixed(1) + 'k'
  return num.toString()
}

function getLangColor(lang: string): string {
  const colors: Record<string, string> = {
    Python: '#3572A5', TypeScript: '#2b7489', JavaScript: '#f1e05a',
    Rust: '#dea584', Go: '#00ADD8', Java: '#b07219',
  }
  return colors[lang] || '#8888a8'
}
</script>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  z-index: 100;
  display: flex;
  justify-content: flex-end;
}

.drawer {
  width: 480px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
  overflow-y: auto;
  padding: 24px;
  transform: translateX(100%);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
}
.drawer.open { transform: translateX(0); }

.close-btn {
  position: absolute;
  top: 16px; right: 16px;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.close-btn:hover { color: var(--text-primary); border-color: var(--text-muted); }

.drawer-loading {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}
.loading-dots { display: flex; gap: 6px; }
.loading-dots span {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: bounce 1.2s infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.4; }
  40% { transform: scale(1.2); opacity: 1; }
}

.drawer-header {
  margin-bottom: 16px;
  padding-right: 32px;
}
.drawer-repo-name {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.mono { font-family: 'Geist Mono', monospace; }
.muted { color: var(--text-muted); font-size: 14px; }
.name { font-size: 18px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
.cn-badge {
  font-size: 9px; font-weight: 700;
  color: var(--cyan); border: 1px solid var(--cyan);
  border-radius: 3px; padding: 0 3px; line-height: 1.4;
}
.drawer-actions { display: flex; gap: 8px; }
.action-btn {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; padding: 6px 12px;
  border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg-elevated); color: var(--text-secondary);
  text-decoration: none; transition: all 0.15s;
}
.action-btn:hover { border-color: var(--accent); color: var(--accent); }
.action-btn.primary { background: var(--accent-glow); border-color: var(--accent); color: var(--accent); }

.drawer-tags {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-bottom: 20px;
}
.cat-tag {
  font-size: 11px; padding: 3px 8px;
  background: var(--accent-glow); border: 1px solid rgba(99,102,241,0.3);
  border-radius: 4px; color: var(--accent);
}
.topic-tag {
  font-size: 11px; padding: 3px 8px;
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-muted);
}

.stats-row {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 8px; margin-bottom: 24px;
}
.stat-box {
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px 12px;
  display: flex; align-items: flex-start; gap: 8px;
}
.stat-icon { margin-top: 2px; color: var(--text-muted); flex-shrink: 0; }
.stat-icon.amber { color: var(--amber); }
.stat-icon.green { color: var(--green); }
.stat-icon.accent { color: var(--accent); }
.stat-num { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

.drawer-section { margin-bottom: 20px; }
.section-title {
  font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--text-muted);
  margin-bottom: 8px;
}
.desc-text { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.desc-original {
  font-size: 11px; color: var(--text-muted);
  margin-top: 6px; font-style: italic;
}

/* 趋势图 */
.trend-chart { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 6px; padding: 12px; }
.chart-bars {
  display: flex; align-items: flex-end; gap: 2px;
  height: 60px; margin-bottom: 6px;
}
.chart-bar-wrap { flex: 1; display: flex; align-items: flex-end; height: 100%; }
.chart-bar {
  width: 100%; min-height: 4px;
  background: var(--border); border-radius: 2px 2px 0 0;
  transition: height 0.3s ease;
}
.chart-bar.highlight { background: var(--accent); }
.chart-labels {
  display: flex; justify-content: space-between;
  font-size: 10px; color: var(--text-muted);
}

.lang-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-secondary);
  background: var(--bg-elevated); border: 1px solid var(--border);
  border-radius: 4px; padding: 4px 10px;
}
.lang-dot { width: 8px; height: 8px; border-radius: 50%; }
</style>
