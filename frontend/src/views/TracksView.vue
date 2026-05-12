<template>
  <div class="layout">
    <AppSidebar :active-view="'tracks'" :track-count="tracks.length" @navigate="onNavigate" />

    <main class="main">
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">🎯 自定义追踪</h1>
          <span class="total-badge mono">{{ tracks.length }} 条规则</span>
        </div>
      </header>

      <!-- 添加表单 -->
      <div class="add-section">
        <!-- Tab 切换 -->
        <div class="tab-bar">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab-btn"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- 追踪 Repo -->
        <form v-if="activeTab === 'repo'" class="add-form" @submit.prevent="submitRepo">
          <div class="form-row">
            <input
              v-model="repoInput"
              class="form-input flex-1"
              placeholder="GitHub URL 或 owner/repo，例如 https://github.com/obra/superpowers"
              required
            />
            <input
              v-model="repoDesc"
              class="form-input desc-input"
              placeholder="备注（可选）"
            />
            <button class="add-btn" :class="{ loading: submitting }" :disabled="submitting" type="submit">
              <PlusIcon :size="13" />
              {{ submitting ? '添加中...' : '添加' }}
            </button>
          </div>
          <div v-if="repoError" class="form-error">{{ repoError }}</div>
        </form>

        <!-- 追踪关键词 -->
        <form v-else-if="activeTab === 'keyword'" class="add-form" @submit.prevent="submitKeyword">
          <div class="form-row">
            <input
              v-model="kwInput"
              class="form-input flex-1"
              placeholder="关键词，例如 agentic skills"
              required
            />
            <div class="stars-input-wrap">
              <StarIcon :size="12" />
              <input
                v-model.number="kwMinStars"
                class="form-input stars-input"
                type="number"
                min="0"
                placeholder="最低 ⭐"
              />
            </div>
            <input
              v-model="kwDesc"
              class="form-input desc-input"
              placeholder="备注（可选）"
            />
            <button class="add-btn" :class="{ loading: submitting }" :disabled="submitting" type="submit">
              <PlusIcon :size="13" />
              {{ submitting ? '添加中...' : '添加' }}
            </button>
          </div>
          <div v-if="kwError" class="form-error">{{ kwError }}</div>
        </form>

        <!-- 追踪 Topic -->
        <form v-else-if="activeTab === 'topic'" class="add-form" @submit.prevent="submitTopic">
          <div class="form-row">
            <input
              v-model="topicInput"
              class="form-input flex-1"
              placeholder="GitHub Topic，例如 llm-agent"
              required
            />
            <div class="stars-input-wrap">
              <StarIcon :size="12" />
              <input
                v-model.number="topicMinStars"
                class="form-input stars-input"
                type="number"
                min="0"
                placeholder="最低 ⭐"
              />
            </div>
            <input
              v-model="topicDesc"
              class="form-input desc-input"
              placeholder="备注（可选）"
            />
            <button class="add-btn" :class="{ loading: submitting }" :disabled="submitting" type="submit">
              <PlusIcon :size="13" />
              {{ submitting ? '添加中...' : '添加' }}
            </button>
          </div>
          <div v-if="topicError" class="form-error">{{ topicError }}</div>
        </form>
      </div>

      <!-- 追踪列表 -->
      <div v-if="loadingTracks" class="loading-state">
        <div class="loading-dots"><span></span><span></span><span></span></div>
      </div>

      <div v-else-if="tracks.length === 0" class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-text">还没有追踪规则</div>
        <div class="empty-sub">添加 Repo、关键词或 Topic，下次爬取时自动收录</div>
      </div>

      <div v-else class="tracks-list">
        <div
          v-for="track in tracks"
          :key="track.id"
          class="track-card"
          :class="{ inactive: !track.is_active }"
        >
          <div class="track-left">
            <span class="track-type-badge" :class="track.track_type">
              {{ typeLabel(track.track_type) }}
            </span>
            <div class="track-info">
              <div class="track-name">{{ track.value }}</div>
              <div v-if="track.description" class="track-desc">{{ track.description }}</div>
              <div class="track-meta mono">
                <span v-if="track.track_type !== 'repo'">
                  ⭐ ≥
                  <input
                    v-if="editingStars === track.id"
                    class="stars-edit-input"
                    type="number" min="0"
                    :value="track.min_stars"
                    @blur="saveStars(track, $event)"
                    @keyup.enter="saveStars(track, $event)"
                    @keyup.escape="editingStars = null"
                    ref="starsInput"
                    autofocus
                  />
                  <span v-else class="stars-value" @click="startEditStars(track.id)">{{ track.min_stars ?? 100 }} <PencilIcon :size="10" class="edit-icon" /></span>
                </span>
                <span>{{ formatDate(track.created_at) }}</span>
              </div>
            </div>
          </div>
          <div class="track-actions">
            <button
              class="toggle-btn"
              :class="{ active: track.is_active }"
              :title="track.is_active ? '点击禁用' : '点击启用'"
              @click="toggleTrack(track)"
            >
              {{ track.is_active ? '启用中' : '已禁用' }}
            </button>
            <button class="del-btn" title="删除" @click="deleteTrack(track.id)">
              <Trash2Icon :size="13" />
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PlusIcon, StarIcon, Trash2Icon, PencilIcon } from 'lucide-vue-next'
import AppSidebar from '@/components/AppSidebar.vue'
import { api } from '@/api'

interface Track {
  id: number
  track_type: 'repo' | 'keyword' | 'topic'
  value: string
  description: string
  min_stars: number | null
  is_active: boolean
  created_at: string
}

const router = useRouter()

const tabs: { key: 'repo' | 'keyword' | 'topic'; label: string }[] = [
  { key: 'repo', label: '📦 追踪 Repo' },
  { key: 'keyword', label: '🔍 追踪关键词' },
  { key: 'topic', label: '🏷️ 追踪 Topic' },
]
const activeTab = ref<'repo' | 'keyword' | 'topic'>('repo')

const tracks = ref<Track[]>([])
const loadingTracks = ref(false)
const submitting = ref(false)

// repo 表单
const repoInput = ref('')
const repoDesc = ref('')
const repoError = ref('')

// keyword 表单
const kwInput = ref('')
const kwMinStars = ref(100)
const kwDesc = ref('')
const kwError = ref('')

// topic 表单
const topicInput = ref('')
const topicMinStars = ref(100)
const topicDesc = ref('')
const topicError = ref('')

async function loadTracks() {
  loadingTracks.value = true
  try {
    const res = await api.getTracks()
    tracks.value = res.data
  } finally {
    loadingTracks.value = false
  }
}

async function submitRepo() {
  repoError.value = ''
  submitting.value = true
  try {
    await api.addRepoTrack(repoInput.value, repoDesc.value)
    repoInput.value = ''
    repoDesc.value = ''
    await loadTracks()
  } catch (e: any) {
    repoError.value = e?.response?.data?.detail || '添加失败，请检查输入'
  } finally {
    submitting.value = false
  }
}

async function submitKeyword() {
  kwError.value = ''
  submitting.value = true
  try {
    await api.addKeywordTrack(kwInput.value, kwMinStars.value)
    kwInput.value = ''
    kwMinStars.value = 100
    kwDesc.value = ''
    await loadTracks()
  } catch (e: any) {
    kwError.value = e?.response?.data?.detail || '添加失败'
  } finally {
    submitting.value = false
  }
}

async function submitTopic() {
  topicError.value = ''
  submitting.value = true
  try {
    await api.addTopicTrack(topicInput.value, topicMinStars.value, topicDesc.value)
    topicInput.value = ''
    topicMinStars.value = 100
    topicDesc.value = ''
    await loadTracks()
  } catch (e: any) {
    topicError.value = e?.response?.data?.detail || '添加失败'
  } finally {
    submitting.value = false
  }
}

const editingStars = ref<number | null>(null)

function startEditStars(id: number) {
  editingStars.value = id
}

async function saveStars(track: Track, event: Event) {
  const val = parseInt((event.target as HTMLInputElement).value)
  if (!isNaN(val) && val !== track.min_stars) {
    await api.updateTrackStars(track.id, val)
    track.min_stars = val
  }
  editingStars.value = null
}

async function toggleTrack(track: Track) {
  await api.toggleTrack(track.id, !track.is_active)
  track.is_active = !track.is_active
}

async function deleteTrack(id: number) {
  if (!confirm('确认删除这条追踪规则？')) return
  await api.deleteTrack(id)
  tracks.value = tracks.value.filter(t => t.id !== id)
}

function typeLabel(type: string) {
  return { repo: 'Repo', keyword: '关键词', topic: 'Topic' }[type] ?? type
}

function formatDate(s: string) {
  if (!s) return ''
  return new Date(s).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

onMounted(loadTracks)

function onNavigate(view: string) {
  if (view === 'home') router.push('/')
  if (view === 'settings') router.push('/settings')
}
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
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 20px;
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

/* 添加区域 */
.add-section {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
}
.tab-btn {
  padding: 5px 12px;
  border-radius: 5px;
  font-size: 12px;
  border: 1px solid transparent;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.tab-btn.active {
  background: var(--accent-glow);
  border-color: var(--accent);
  color: var(--accent);
}

.add-form {}
.form-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.form-input {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.15s;
}
.form-input:focus { border-color: var(--accent); }
.form-input::placeholder { color: var(--text-muted); }
.form-input.flex-1 { flex: 1; min-width: 200px; }
.form-input.desc-input { width: 140px; }
.form-input.stars-input { width: 80px; }

.stars-input-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0 8px;
  color: var(--text-muted);
}
.stars-input-wrap .form-input {
  border: none;
  background: none;
  padding: 7px 0;
}
.stars-input-wrap .form-input:focus { border: none; }

.add-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 12px;
  background: var(--accent);
  color: #fff;
  border: none;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}
.add-btn:hover { opacity: 0.85; }
.add-btn.loading, .add-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.form-error {
  margin-top: 8px;
  font-size: 12px;
  color: #f87171;
}

/* 列表 */
.tracks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.track-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  transition: border-color 0.15s;
}
.track-card:hover { border-color: var(--border-hover, var(--accent)); }
.track-card.inactive { opacity: 0.5; }

.track-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.track-type-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
  margin-top: 2px;
}
.track-type-badge.repo { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
.track-type-badge.keyword { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
.track-type-badge.topic { background: #fff7ed; color: #d97706; border: 1px solid #fed7aa; }

.track-info { flex: 1; min-width: 0; }
.track-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.track-meta {
  display: flex;
  gap: 10px;
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 4px;
  align-items: center;
}
.stars-value {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 4px;
  border-radius: 3px;
  transition: background 0.15s;
}
.stars-value:hover { background: var(--bg-hover); }
.edit-icon { opacity: 0; transition: opacity 0.15s; }
.stars-value:hover .edit-icon { opacity: 1; }
.stars-edit-input {
  width: 52px; font-size: 10px;
  background: var(--bg-elevated); border: 1px solid var(--accent);
  border-radius: 3px; color: var(--text-primary);
  padding: 1px 4px; outline: none;
  font-family: 'Geist Mono', monospace;
}

.track-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.toggle-btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.toggle-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-glow);
}

.del-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.del-btn:hover { border-color: #f87171; color: #f87171; background: rgba(248,113,113,0.08); }

/* 状态 */
.loading-state {
  display: flex;
  justify-content: center;
  padding: 60px 0;
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

.empty-state {
  text-align: center;
  padding: 80px 20px;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 16px; color: var(--text-secondary); margin-bottom: 6px; }
.empty-sub { font-size: 13px; color: var(--text-muted); }
</style>
