<template>
  <div class="layout">
    <!-- 侧边栏 -->
    <AppSidebar :active-view="'home'" :track-count="trackCount" @navigate="onNavigate" />

    <!-- 主内容区 -->
    <main class="main">
      <!-- 顶部栏 -->
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">
            {{ store.currentCategory?.icon || '🌐' }}
            {{ store.currentCategory?.name || '全部 AI 项目' }}
          </h1>
          <span class="total-badge mono">{{ displayTotal }} 个项目</span>
        </div>
        <div class="topbar-right">
          <!-- 搜索框 -->
          <div class="search-box" :class="{ active: searchQuery }">
            <SearchIcon :size="13" :class="{ 'spin': searching }" />
            <input v-model="searchQuery" placeholder="搜索全部项目..." class="search-input" />
          </div>
          <!-- 语言切换 -->
          <button class="lang-btn" @click="store.lang = store.lang === 'zh' ? 'en' : 'zh'"
            :title="store.lang === 'zh' ? '切换为英文' : '切换为中文'">
            <span class="lang-flag">{{ store.lang === 'zh' ? '🇨🇳' : '🇺🇸' }}</span>
            {{ store.lang === 'zh' ? '中文' : 'English' }}
          </button>
          <!-- 触发爬取 -->
          <button class="crawl-btn" :class="{ loading: crawling }" @click="triggerCrawl">
            <RefreshCwIcon :size="13" :class="{ 'spin': crawling }" />
            {{ crawling ? '抓取中...' : '立即抓取' }}
          </button>
        </div>
      </header>

      <!-- 概览卡片 -->
      <div class="overview-strip">
        <div class="ov-card">
          <div class="ov-label">今日热度</div>
          <div class="ov-value mono accent">{{ store.overview?.trending_today ?? '—' }}</div>
        </div>
        <div class="ov-card">
          <div class="ov-label">收录总数</div>
          <div class="ov-value mono">{{ store.overview?.total_repos_all ?? '—' }}</div>
        </div>
        <div class="ov-card">
          <div class="ov-label">今日新增 ⭐</div>
          <div class="ov-value mono amber">{{ formatNum(store.overview?.total_stars_today ?? 0) }}</div>
        </div>
        <div class="ov-card">
          <div class="ov-label">当前分类</div>
          <div class="ov-value mono">{{ store.currentCategory?.name || '全部' }}</div>
        </div>
      </div>

      <!-- repo 列表 -->
      <div class="repo-grid" ref="gridRef">
        <!-- 骨架屏 -->
        <template v-if="store.loading && store.repos.length === 0">
          <div v-for="i in 12" :key="i" class="skeleton-card">
            <div class="skeleton" style="height:14px;width:60%;margin-bottom:8px"></div>
            <div class="skeleton" style="height:12px;width:90%;margin-bottom:4px"></div>
            <div class="skeleton" style="height:12px;width:70%"></div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else-if="!store.loading && filteredRepos.length === 0" class="empty-state">
          <div class="empty-icon">🔭</div>
          <div class="empty-text">暂无数据</div>
          <div class="empty-sub">尝试切换分类或触发一次抓取</div>
        </div>

        <!-- 卡片列表 -->
        <RepoCard
          v-for="(repo, i) in filteredRepos"
          :key="repo.id"
          :repo="repo"
          :style="{ animationDelay: `${Math.min(i, 20) * 30}ms` }"
          @click="openDetail"
        />
      </div>

      <!-- 加载更多 -->
      <div class="load-more-area" ref="loadMoreRef">
        <div v-if="store.loading && store.repos.length > 0" class="loading-dots">
          <span></span><span></span><span></span>
        </div>
        <div v-else-if="!searchQuery && store.repos.length >= store.total && store.total > 0"
             class="all-loaded mono">
          ── 已加载全部 {{ store.total }} 个项目 ──
        </div>
      </div>
    </main>

    <!-- 详情抽屉 -->
    <RepoDrawer v-if="selectedRepo" :repo-name="selectedRepo" @close="selectedRepo = ''" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useIntersectionObserver } from '@vueuse/core'
import { SearchIcon, RefreshCwIcon } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'
import { api, type Repo } from '@/api'
import AppSidebar from '@/components/AppSidebar.vue'
import RepoCard from '@/components/RepoCard.vue'
import RepoDrawer from '@/components/RepoDrawer.vue'

const store = useAppStore()
const router = useRouter()
const trackCount = ref(0)

async function loadTrackCount() {
  try {
    const res = await api.getTracks()
    trackCount.value = (res.data as any[]).filter((t: any) => t.is_active).length
  } catch { /* ignore */ }
}
const searchQuery = ref('')
const searchResults = ref<Repo[]>([])
const searchTotal = ref(0)
const searching = ref(false)
let searchTimer: ReturnType<typeof setTimeout>
const crawling = ref(false)
const selectedRepo = ref('')
const loadMoreRef = ref<HTMLElement>()

// 搜索时用后端全量搜索，否则用 store 列表
const filteredRepos = computed(() =>
  searchQuery.value.trim() ? searchResults.value : store.repos
)
const displayTotal = computed(() =>
  searchQuery.value.trim() ? searchTotal.value : store.total
)

watch(searchQuery, () => {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) { searchResults.value = []; return }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const res = await api.searchRepos(searchQuery.value.trim())
      searchResults.value = res.data.items
      searchTotal.value = res.data.total
    } finally { searching.value = false }
  }, 400)
})

// 无限滚动
useIntersectionObserver(loadMoreRef, (entries) => {
  const entry = entries[0]
  if (entry?.isIntersecting && !store.loading) {
    store.loadMore()
  }
})

function formatNum(n: number) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return n.toString()
}

function openDetail(repo: Repo) {
  selectedRepo.value = repo.full_name
}
async function triggerCrawl() {
  if (crawling.value) return
  crawling.value = true
  try {
    await api.triggerCrawl()
    setTimeout(() => {
      store.loadRepos(true)
      store.loadOverview()
    }, 3000)
  } finally {
    setTimeout(() => { crawling.value = false }, 5000)
  }
}

function onNavigate(view: string) {
  if (view === 'tracks') router.push('/tracks')
  if (view === 'settings') router.push('/settings')
}

onMounted(async () => {
  await store.loadCategories()
  await store.loadOverview()
  await store.loadRepos(true)
  loadTrackCount()
})
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 0 24px 40px;
  overflow-x: hidden;
}

/* 顶部栏 */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 16px;
  gap: 16px;
  flex-wrap: wrap;
}
.topbar-left { display: flex; align-items: center; gap: 10px; }
.page-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.03em;
}
.total-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 7px;
}
.topbar-right { display: flex; align-items: center; gap: 8px; }

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  color: var(--text-muted);
  transition: border-color 0.15s;
}
.search-box:focus-within { border-color: var(--accent); color: var(--text-secondary); }
.search-input {
  background: none;
  border: none;
  outline: none;
  font-size: 12px;
  color: var(--text-primary);
  width: 160px;
}
.search-input::placeholder { color: var(--text-muted); }

.lang-btn {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.lang-btn:hover { border-color: var(--accent); color: var(--accent); }
.lang-flag { font-size: 13px; }

.crawl-btn {  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.crawl-btn:hover { border-color: var(--accent); color: var(--accent); }
.crawl-btn.loading { opacity: 0.6; cursor: not-allowed; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 概览条 */
.overview-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 20px;
}
.ov-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 14px;
}
.ov-label { font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; letter-spacing: 0.01em; }
.ov-value { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.ov-value.accent { color: var(--accent); }
.ov-value.amber { color: var(--amber); }

/* repo 网格 */
.repo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 10px;
}

.skeleton-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  height: 120px;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 80px 20px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 16px; color: var(--text-secondary); margin-bottom: 6px; }
.empty-sub { font-size: 13px; color: var(--text-muted); }

/* 加载更多 */
.load-more-area {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}
.loading-dots {
  display: flex;
  gap: 6px;
  align-items: center;
}
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
.all-loaded {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.05em;
}

@media (max-width: 768px) {
  .overview-strip { grid-template-columns: repeat(2, 1fr); }
  .repo-grid { grid-template-columns: 1fr; }
}
</style>
