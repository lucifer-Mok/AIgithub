import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, type Category, type Overview, type Repo } from '@/api'

export const useAppStore = defineStore('app', () => {
  // 状态
  const categories = ref<Category[]>([])
  const overview = ref<Overview | null>(null)
  const repos = ref<Repo[]>([])
  const total = ref(0)
  const loading = ref(false)
  const selectedCategory = ref<string>('')
  const selectedDate = ref<string>('')
  const sortBy = ref<string>('stars_today')
  const order = ref<'asc' | 'desc'>('desc')
  const favoritesOnly = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const lang = ref<'zh' | 'en'>('zh')
  const hasDeepSeek = ref(false)  // 是否配置了 DeepSeek Key，全局只查一次

  // 计算属性
  const currentCategory = computed(() =>
    categories.value.find(c => c.slug === selectedCategory.value)
  )

  // 加载分类
  async function loadCategories() {
    const res = await api.getCategories()
    categories.value = res.data
    // 同时检查 DeepSeek 配置
    try {
      const cfg = await api.getConfig()
      hasDeepSeek.value = (cfg.data as any).DEEPSEEK_API_KEY?.is_set ?? false
    } catch { /* ignore */ }
  }

  // 加载概览，后端会自动回退到最近有数据的日期
  async function loadOverview(date?: string) {
    const res = await api.getOverview(date, sortBy.value, favoritesOnly.value || undefined)
    overview.value = res.data
    // 同步前端选中的日期
    if (!date && res.data.date) {
      selectedDate.value = res.data.date
    }
  }

  // 加载 repo 列表
  async function loadRepos(reset = false) {
    if (reset) page.value = 1
    loading.value = true
    try {
      const res = await api.getRepos({
        category: selectedCategory.value || undefined,
        date: selectedDate.value || undefined,
        sort: sortBy.value,
        order: order.value,
        page: page.value,
        page_size: pageSize.value,
        favorites_only: favoritesOnly.value || undefined,
      })
      if (reset) {
        repos.value = res.data.items
      } else {
        repos.value.push(...res.data.items)
      }
      total.value = res.data.total
    } finally {
      loading.value = false
    }
  }

  // 加载更多
  async function loadMore() {
    if (repos.value.length >= total.value) return
    page.value++
    await loadRepos(false)
  }

  // 切换分类
  async function setCategory(slug: string) {
    selectedCategory.value = slug
    await loadRepos(true)
  }

  // 切换排序：点同一个则反转方向，点不同的则重置为 desc
  async function setSort(sort: string) {
    if (sortBy.value === sort) {
      order.value = order.value === 'desc' ? 'asc' : 'desc'
    } else {
      sortBy.value = sort
      order.value = 'desc'
    }
    if (sort !== 'stars_today') selectedDate.value = ''
    pageSize.value = sort === 'stars_today' ? 20 : 40
    await Promise.all([loadRepos(true), loadOverview()])
  }

  async function setFavoritesOnly(value: boolean) {
    favoritesOnly.value = value
    await Promise.all([loadRepos(true), loadOverview()])
  }

  function updateFavorite(fullName: string, isFavorite: boolean) {
    repos.value = repos.value.map(repo =>
      repo.full_name === fullName ? { ...repo, is_favorite: isFavorite } : repo
    )
    if (favoritesOnly.value && !isFavorite) {
      repos.value = repos.value.filter(repo => repo.full_name !== fullName)
      total.value = Math.max(0, total.value - 1)
    }
    loadOverview()
  }

  return {
    categories, overview, repos, total, loading,
    selectedCategory, selectedDate, sortBy, order, favoritesOnly, page, pageSize, lang, hasDeepSeek,
    currentCategory,
    loadCategories, loadOverview, loadRepos, loadMore,
    setCategory, setSort, setFavoritesOnly, updateFavorite,
  }
})
