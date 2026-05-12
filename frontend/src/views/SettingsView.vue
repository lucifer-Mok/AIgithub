<template>
  <div class="layout">
    <AppSidebar :active-view="'settings'" :track-count="0" @navigate="onNavigate" />

    <main class="main">
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">⚙️ 系统设置</h1>
          <span class="sub-title">修改后立即生效，无需重启服务</span>
        </div>
      </header>

      <div v-if="loading" class="loading-state">
        <div class="loading-dots"><span></span><span></span><span></span></div>
      </div>

      <div v-else class="settings-list">

        <!-- GitHub Token -->
        <div class="setting-card">
          <div class="setting-header">
            <div class="setting-title">
              <span class="setting-icon">🔑</span>
              GitHub Token
              <span class="badge" :class="configs.GITHUB_TOKEN?.is_set ? 'badge-green' : 'badge-gray'">
                {{ configs.GITHUB_TOKEN?.is_set ? '已配置' : '未配置' }}
              </span>
              <!-- 验证状态 -->
              <span v-if="tokenStatus.checking" class="badge badge-gray">验证中...</span>
              <span v-else-if="tokenStatus.valid === true" class="badge badge-green">✓ 有效</span>
              <span v-else-if="tokenStatus.valid === false" class="badge badge-red"
                :title="tokenStatus.reason">✗ 已失效</span>
              <button v-if="configs.GITHUB_TOKEN?.is_set && tokenStatus.valid !== null"
                class="verify-btn" @click="verifyToken">重新验证</button>
            </div>
            <div class="setting-desc">
              用于 Search API 认证。无 Token 限 60次/小时，有 Token 限 5000次/小时。
              <a href="https://github.com/settings/tokens/new" target="_blank" class="link">
                去生成 →
              </a>
            </div>
          </div>
          <div class="setting-input-row">
            <input
              v-model="inputs.GITHUB_TOKEN"
              class="setting-input"
              :type="showSecrets.GITHUB_TOKEN ? 'text' : 'password'"
              placeholder="ghp_xxxx 或 github_pat_xxxx"
            />
            <button class="eye-btn" @click="toggleSecret('GITHUB_TOKEN')">
              {{ showSecrets.GITHUB_TOKEN ? '🙈' : '👁️' }}
            </button>
            <button class="save-btn" :class="{ loading: saving.GITHUB_TOKEN }"
              @click="save('GITHUB_TOKEN')">
              {{ saving.GITHUB_TOKEN ? '保存中...' : '保存' }}
            </button>
            <button v-if="configs.GITHUB_TOKEN?.is_set" class="clear-btn"
              @click="clear('GITHUB_TOKEN')">
              清空
            </button>
          </div>
          <div v-if="messages.GITHUB_TOKEN" class="setting-msg"
            :class="messages.GITHUB_TOKEN.ok ? 'msg-ok' : 'msg-err'">
            {{ messages.GITHUB_TOKEN.text }}
          </div>
        </div>

        <!-- DeepSeek API Key -->
        <div class="setting-card">
          <div class="setting-header">
            <div class="setting-title">
              <span class="setting-icon">🤖</span>
              DeepSeek API Key
              <span class="badge" :class="configs.DEEPSEEK_API_KEY?.is_set ? 'badge-green' : 'badge-gray'">
                {{ configs.DEEPSEEK_API_KEY?.is_set ? '已配置' : '未配置' }}
              </span>
            </div>
            <div class="setting-desc">
              用于高质量中文摘要生成。未配置时自动降级为 Google 免费翻译。
              <a href="https://platform.deepseek.com/api_keys" target="_blank" class="link">
                去获取 →
              </a>
            </div>
          </div>
          <div class="setting-input-row">
            <input
              v-model="inputs.DEEPSEEK_API_KEY"
              class="setting-input"
              :type="showSecrets.DEEPSEEK_API_KEY ? 'text' : 'password'"
              placeholder="sk-xxxx"
            />
            <button class="eye-btn" @click="toggleSecret('DEEPSEEK_API_KEY')">
              {{ showSecrets.DEEPSEEK_API_KEY ? '🙈' : '👁️' }}
            </button>
            <button class="save-btn" :class="{ loading: saving.DEEPSEEK_API_KEY }"
              @click="save('DEEPSEEK_API_KEY')">
              {{ saving.DEEPSEEK_API_KEY ? '保存中...' : '保存' }}
            </button>
            <button v-if="configs.DEEPSEEK_API_KEY?.is_set" class="clear-btn"
              @click="clear('DEEPSEEK_API_KEY')">
              清空
            </button>
          </div>
          <div v-if="messages.DEEPSEEK_API_KEY" class="setting-msg"
            :class="messages.DEEPSEEK_API_KEY.ok ? 'msg-ok' : 'msg-err'">
            {{ messages.DEEPSEEK_API_KEY.text }}
          </div>
        </div>

        <!-- DeepSeek 模型 -->
        <div class="setting-card">
          <div class="setting-header">
            <div class="setting-title">
              <span class="setting-icon">🧠</span>
              DeepSeek 模型
            </div>
            <div class="setting-desc">默认 deepseek-chat，也可以用 deepseek-reasoner</div>
          </div>
          <div class="setting-input-row">
            <input v-model="inputs.DEEPSEEK_MODEL" class="setting-input" placeholder="deepseek-chat" />
            <button class="save-btn" :class="{ loading: saving.DEEPSEEK_MODEL }"
              @click="save('DEEPSEEK_MODEL')">
              {{ saving.DEEPSEEK_MODEL ? '保存中...' : '保存' }}
            </button>
          </div>
          <div v-if="messages.DEEPSEEK_MODEL" class="setting-msg"
            :class="messages.DEEPSEEK_MODEL.ok ? 'msg-ok' : 'msg-err'">
            {{ messages.DEEPSEEK_MODEL.text }}
          </div>
        </div>

        <!-- 提示 -->
        <div class="info-card">
          <div class="info-icon">💡</div>
          <div class="info-text">
            所有配置直接写入 <code>.env</code> 文件并立即热加载，无需重启后端服务。
            下次爬取时自动使用新配置。
          </div>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import { api } from '@/api'

const router = useRouter()
const loading = ref(true)
const configs = ref<Record<string, { value: string; is_set: boolean; is_secret: boolean }>>({})
const inputs = reactive<Record<string, string>>({
  GITHUB_TOKEN: '',
  DEEPSEEK_API_KEY: '',
  DEEPSEEK_MODEL: '',
})
const saving = reactive<Record<string, boolean>>({})
const messages = reactive<Record<string, { ok: boolean; text: string } | null>>({})
const showSecrets = reactive<Record<string, boolean>>({
  GITHUB_TOKEN: false,
  DEEPSEEK_API_KEY: false,
})
const tokenStatus = ref({ checking: false, valid: null as boolean | null, reason: '' })

async function loadConfig() {
  loading.value = true
  try {
    const res = await api.getConfig()
    configs.value = res.data
    for (const [key, cfg] of Object.entries(res.data as any)) {
      if (!(cfg as any).is_secret && (cfg as any).value) {
        inputs[key] = (cfg as any).value
      }
    }
    // 加载后自动验证 GitHub Token
    if ((res.data as any).GITHUB_TOKEN?.is_set) {
      verifyToken()
    }
  } finally {
    loading.value = false
  }
}

async function verifyToken() {
  tokenStatus.value.checking = true
  tokenStatus.value.valid = null
  try {
    const res = await api.verifyGithubToken()
    tokenStatus.value.valid = res.data.valid
    tokenStatus.value.reason = res.data.reason
  } catch {
    tokenStatus.value.valid = false
    tokenStatus.value.reason = '验证请求失败'
  } finally {
    tokenStatus.value.checking = false
  }
}

async function save(key: string) {
  if (!inputs[key]?.trim()) return
  saving[key] = true
  messages[key] = null
  try {
    await api.updateConfig(key, inputs[key].trim())
    configs.value[key] = { ...configs.value[key], is_set: true, value: configs.value[key]?.value ?? '', is_secret: configs.value[key]?.is_secret ?? false }
    messages[key] = { ok: true, text: '✓ 已保存并生效' }
    if (showSecrets[key]) inputs[key] = ''
    setTimeout(() => { messages[key] = null }, 3000)
    // 保存 Token 后重新验证
    if (key === 'GITHUB_TOKEN') setTimeout(verifyToken, 500)
  } catch (e: any) {
    messages[key] = { ok: false, text: e?.response?.data?.detail || '保存失败' }
  } finally {
    saving[key] = false
  }
}

async function clear(key: string) {
  if (!confirm(`确认清空 ${key}？`)) return
  try {
    await api.clearConfig(key)
    configs.value[key] = { ...configs.value[key], is_set: false, value: '', is_secret: configs.value[key]?.is_secret ?? false }
    inputs[key] = ''
    messages[key] = { ok: true, text: '已清空' }
    setTimeout(() => { messages[key] = null }, 2000)
  } catch (e: any) {
    messages[key] = { ok: false, text: '清空失败' }
  }
}

function toggleSecret(key: string) {
  showSecrets[key] = !showSecrets[key]
}

function onNavigate(view: string) {
  if (view === 'home') router.push('/')
  if (view === 'tracks') router.push('/tracks')
}

onMounted(loadConfig)
</script>

<style scoped>
.layout { display: flex; min-height: 100vh; }
.main { flex: 1; min-width: 0; padding: 0 24px 40px; }

.topbar {
  display: flex; align-items: center;
  padding: 18px 0 16px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 24px; gap: 12px;
}
.topbar-left { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 18px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.03em; }
.sub-title { font-size: 12px; color: var(--text-muted); }

.settings-list { display: flex; flex-direction: column; gap: 12px; max-width: 680px; }

.setting-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 20px;
}
.setting-header { margin-bottom: 12px; }
.setting-title {
  display: flex; align-items: center; gap: 7px;
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 5px;
}
.setting-icon { font-size: 15px; }
.setting-desc { font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.link { color: var(--accent); text-decoration: none; }
.link:hover { text-decoration: underline; }

.badge {
  font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 10px;
}
.badge-green { background: #dcfce7; color: #15803d; }
.badge-gray { background: var(--bg-hover); color: var(--text-muted); }
.badge-red { background: #fee2e2; color: #b91c1c; cursor: help; }

.verify-btn {
  font-size: 10px; padding: 2px 8px;
  border-radius: 4px; border: 1px solid var(--border);
  background: none; color: var(--text-muted);
  cursor: pointer; transition: all 0.15s; margin-left: 4px;
}
.verify-btn:hover { border-color: var(--accent); color: var(--accent); }

.setting-input-row {
  display: flex; align-items: center; gap: 8px;
}
.setting-input {
  flex: 1;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  padding: 8px 12px;
  outline: none;
  font-family: 'Geist Mono', monospace;
  transition: border-color 0.15s;
}
.setting-input:focus { border-color: var(--accent); }
.setting-input::placeholder { color: var(--text-muted); font-family: 'Geist', sans-serif; }

.eye-btn {
  padding: 6px 8px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-base);
  cursor: pointer; font-size: 14px; transition: all 0.15s;
}
.eye-btn:hover { border-color: var(--accent); }

.save-btn {
  padding: 8px 16px; border-radius: 6px;
  background: var(--accent); color: #fff;
  border: none; font-size: 12px; font-weight: 600;
  cursor: pointer; white-space: nowrap; transition: opacity 0.15s;
}
.save-btn:hover { opacity: 0.85; }
.save-btn.loading { opacity: 0.5; cursor: not-allowed; }

.clear-btn {
  padding: 8px 12px; border-radius: 6px;
  background: none; color: var(--text-muted);
  border: 1px solid var(--border); font-size: 12px;
  cursor: pointer; white-space: nowrap; transition: all 0.15s;
}
.clear-btn:hover { border-color: var(--red); color: var(--red); }

.setting-msg {
  margin-top: 8px; font-size: 12px; font-weight: 500;
}
.msg-ok { color: var(--green); }
.msg-err { color: var(--red); }

.info-card {
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--accent-glow);
  border: 1px solid rgba(79,70,229,0.15);
  border-radius: 8px; padding: 12px 16px;
}
.info-icon { font-size: 16px; flex-shrink: 0; }
.info-text { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.info-text code {
  font-family: 'Geist Mono', monospace;
  background: var(--bg-hover); padding: 1px 5px;
  border-radius: 3px; font-size: 11px;
}

.loading-state { display: flex; justify-content: center; padding: 60px 0; }
.loading-dots { display: flex; gap: 6px; }
.loading-dots span {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-muted); animation: bounce 1.2s infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.4; }
  40% { transform: scale(1.2); opacity: 1; }
}
</style>
