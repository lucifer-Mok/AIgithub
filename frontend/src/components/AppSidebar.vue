<template>
  <aside class="sidebar">
    <!-- Logo -->
    <div class="sidebar-logo">
      <div class="logo-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
            stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span class="logo-text">AI Radar</span>
      <span class="logo-badge mono">β</span>
    </div>

    <!-- 日期（只在今日热度模式下显示） -->
    <div v-if="store.sortBy === 'stars_today'" class="sidebar-section">
      <div class="section-label">日期</div>
      <div class="date-display mono" @click="showDatePicker = !showDatePicker">
        {{ displayDate }}
        <CalendarIcon :size="11" />
      </div>
      <input v-if="showDatePicker" type="date" class="date-input"
        :value="store.selectedDate" :max="today"
        @change="onDateChange" @blur="showDatePicker = false" />
    </div>

    <!-- 排序 -->
    <div class="sidebar-section">
      <div class="section-label">排序</div>
      <div class="sort-options">
        <button v-for="opt in sortOptions" :key="opt.value"
          class="sort-btn" :class="{ active: store.sortBy === opt.value }"
          @click="store.setSort(opt.value)">
          <component :is="opt.icon" :size="12" />
          {{ opt.label }}
          <span v-if="store.sortBy === opt.value" class="order-arrow">
            {{ store.order === 'desc' ? '↓' : '↑' }}
          </span>
        </button>
      </div>
    </div>

    <!-- 分类 -->
    <div class="sidebar-section flex-1">
      <div class="section-label">分类</div>
      <nav class="category-nav">
        <button class="cat-item" :class="{ active: store.selectedCategory === '' && activeView === 'home' }"
          @click="goHome('')">
          <span class="cat-icon">🌐</span>
          <span class="cat-name">全部</span>
          <span class="cat-count mono">
            {{ store.sortBy === 'stars_today'
              ? (store.overview?.trending_today ?? 0)
              : (store.overview?.total_repos_all ?? 0) }}
          </span>
        </button>
        <button v-for="cat in store.categories" :key="cat.slug"
          class="cat-item" :class="{ active: store.selectedCategory === cat.slug && activeView === 'home' }"
          @click="goHome(cat.slug)">
          <span class="cat-icon">{{ cat.icon }}</span>
          <span class="cat-name">{{ cat.name }}</span>
          <span class="cat-count mono">{{ getCategoryCount(cat.slug) }}</span>
        </button>
      </nav>
    </div>

    <!-- 追踪管理入口 -->
    <div class="sidebar-section">
      <button class="track-btn" :class="{ active: activeView === 'tracks' }"
        @click="$emit('navigate', 'tracks')">
        <BookmarkIcon :size="13" />
        自定义追踪
        <span v-if="trackCount > 0" class="track-count mono">{{ trackCount }}</span>
      </button>
      <button class="track-btn" style="margin-top:4px" :class="{ active: activeView === 'settings' }"
        @click="$emit('navigate', 'settings')">
        <SettingsIcon :size="13" />
        系统设置
      </button>
    </div>

    <!-- 底部统计 -->
    <div class="sidebar-footer">
      <div class="footer-stat">
        <span class="stat-label">收录总数</span>
        <span class="stat-value mono accent">{{ store.overview?.total_repos_all ?? 0 }}</span>
      </div>
      <div class="footer-stat">
        <span class="stat-label">今日 Trending</span>
        <span class="stat-value mono">{{ store.overview?.trending_today ?? 0 }}</span>
      </div>
      <div class="footer-stat">
        <span class="stat-label">今日新增 ⭐</span>
        <span class="stat-value mono amber">{{ formatNumber(store.overview?.total_stars_today ?? 0) }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { CalendarIcon, TrendingUpIcon, StarIcon, ZapIcon, BookmarkIcon, SettingsIcon } from 'lucide-vue-next'
import { useAppStore } from '@/stores/app'

const props = defineProps<{ activeView: string; trackCount: number }>()
const emit = defineEmits<{ navigate: [view: string] }>()

const store = useAppStore()
const showDatePicker = ref(false)
const today = new Date().toISOString().split('T')[0]

const displayDate = computed(() => {
  if (!store.selectedDate) return '今天'
  const d = new Date(store.selectedDate + 'T00:00:00')
  return `${d.getMonth() + 1}月${d.getDate()}日`
})

const sortOptions = [
  { value: 'stars_today', label: '今日热度', icon: TrendingUpIcon },
  { value: 'stars_total', label: '总星数', icon: StarIcon },
  { value: 'ai_score', label: 'AI 相关度', icon: ZapIcon },
]

function getCategoryCount(slug: string) {
  return store.overview?.categories.find(c => c.slug === slug)?.count ?? 0
}

function formatNumber(n: number) {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return n.toString()
}

function onDateChange(e: Event) {
  const val = (e.target as HTMLInputElement).value
  store.selectedDate = val
  store.loadRepos(true)
  store.loadOverview(val)
  showDatePicker.value = false
}

function goHome(slug: string) {
  emit('navigate', 'home')
  store.setCategory(slug)
}</script>

<style scoped>
.sidebar {
  width: 220px;
  min-width: 220px;
  height: 100vh;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border);
  overflow: hidden;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.logo-icon {
  width: 28px; height: 28px;
  background: var(--accent-glow);
  border: 1px solid rgba(79,70,229,0.2);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent);
  flex-shrink: 0;
}
.logo-text { font-size: 14px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; }
.logo-badge { font-size: 10px; color: var(--text-muted); margin-left: auto; font-weight: 500; }

.sidebar-section {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.sidebar-section.flex-1 { flex: 1; overflow-y: auto; border-bottom: none; }

.section-label {
  font-size: 10px; font-weight: 700;
  letter-spacing: 0.07em; text-transform: uppercase;
  color: var(--text-secondary); margin-bottom: 7px;
}

.date-display {
  font-size: 12px; color: var(--text-secondary);
  cursor: pointer; display: flex; align-items: center; gap: 5px;
  padding: 4px 8px; border-radius: 5px;
  border: 1px solid var(--border); width: fit-content;
  transition: all 0.15s; background: var(--bg-base);
}
.date-display:hover { border-color: var(--accent); color: var(--text-primary); }
.date-input {
  margin-top: 6px; width: 100%;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 5px; color: var(--text-primary);
  font-size: 12px; padding: 4px 8px; outline: none;
}

.sort-options { display: flex; flex-direction: column; gap: 1px; }
.sort-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-radius: 5px;
  font-size: 12px; color: var(--text-secondary);
  background: none; border: none; cursor: pointer;
  text-align: left; transition: all 0.15s; width: 100%;
}
.sort-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.sort-btn.active { background: var(--accent-glow); color: var(--accent); font-weight: 500; }
.order-arrow { margin-left: auto; font-size: 11px; font-weight: 700; }

.category-nav { display: flex; flex-direction: column; gap: 1px; }
.cat-item {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 8px; border-radius: 5px;
  font-size: 12px; color: var(--text-secondary);
  background: none; border: none; cursor: pointer;
  text-align: left; width: 100%; transition: all 0.15s;
}
.cat-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.cat-item.active { background: var(--accent-glow); color: var(--accent); font-weight: 500; }
.cat-icon { font-size: 13px; flex-shrink: 0; }
.cat-name { flex: 1; }
.cat-count {
  font-size: 10px; color: var(--text-muted);
  background: var(--bg-hover); padding: 1px 5px;
  border-radius: 3px; min-width: 18px; text-align: center;
}
.cat-item.active .cat-count { background: rgba(79,70,229,0.1); color: var(--accent); }

.track-btn {
  display: flex; align-items: center; gap: 7px;
  width: 100%; padding: 7px 8px; border-radius: 6px;
  font-size: 12px; color: var(--text-secondary);
  background: var(--bg-base); border: 1px solid var(--border);
  cursor: pointer; transition: all 0.15s;
}
.track-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-glow); }
.track-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-glow); font-weight: 500; }
.track-count {
  margin-left: auto; font-size: 10px;
  background: var(--accent); color: white;
  border-radius: 10px; padding: 0 6px; line-height: 1.6;
}

.sidebar-footer {
  padding: 10px 14px; border-top: 1px solid var(--border-subtle);
  display: flex; flex-direction: column; gap: 5px;
}
.footer-stat { display: flex; justify-content: space-between; align-items: center; }
.stat-label { font-size: 11px; color: var(--text-muted); }
.stat-value { font-size: 12px; color: var(--text-secondary); }
.stat-value.accent { color: var(--accent); font-weight: 600; }
.stat-value.amber { color: var(--amber); font-weight: 600; }
</style>
