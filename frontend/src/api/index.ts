import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export interface Category {
  id: number
  name: string
  slug: string
  description: string
  icon: string
}

export interface Repo {
  id: number
  full_name: string
  owner: string
  repo_name: string
  name_zh: string | null
  description: string
  summary_zh: string | null
  tags_zh: string[]
  language: string
  html_url: string
  stars_total: number
  stars_today: number
  forks_total: number
  topics: string[]
  category_id: number | null
  sub_categories: string[]
  ai_score: number
  rank: number
  has_chinese_readme: boolean
}

export interface RepoDetail extends Repo {
  homepage: string
  category: { name: string; slug: string; icon: string } | null
  trend: { date: string; stars_today: number; stars_total: number; rank: number }[]
}

export interface Overview {
  date: string
  total_repos_today: number
  total_repos_all: number
  trending_today: number
  total_stars_today: number
  categories: { name: string; slug: string; icon: string; count: number }[]
}

export interface RepoListResponse {
  date: string
  total: number
  page: number
  page_size: number
  items: Repo[]
}

export const api = {
  // 分类
  getCategories: () => http.get<Category[]>('/categories'),

  // 概览
  getOverview: (date?: string, sort?: string) =>
    http.get<Overview>('/stats/overview', { params: { date, sort } }),

  // 历史趋势
  getHistory: (days = 30) =>
    http.get<{ date: string; count: number }[]>('/stats/history', { params: { days } }),

  // repo 列表
  getRepos: (params: {
    category?: string
    date?: string
    sort?: string
    order?: string
    page?: number
    page_size?: number
  }) => http.get<RepoListResponse>('/repos', { params }),

  // repo 详情
  getRepo: (fullName: string) =>
    http.get<RepoDetail>(`/repos/${fullName}`),

  // 手动触发爬取
  triggerCrawl: () => http.post('/crawl/trigger'),

  // 爬取日志
  getCrawlLogs: (limit = 10) =>
    http.get('/crawl/logs', { params: { limit } }),

  // 全量搜索
  searchRepos: (q: string, page = 1, page_size = 20) =>
    http.get<RepoListResponse>('/repos/search', { params: { q, page, page_size } }),

  // 按需翻译
  translateRepo: (fullName: string, engine: 'auto' | 'deepseek' | 'google' = 'auto') =>
    http.post(`/repos/${fullName}/translate`, null, { params: { engine } }),

  // 系统配置
  getConfig: () => http.get('/config'),
  updateConfig: (key: string, value: string) =>
    http.post('/config', { key, value }),
  clearConfig: (key: string) =>
    http.delete(`/config/${key}`),
  verifyGithubToken: () =>
    http.get('/config/verify/github'),
  getTracks: () => http.get('/tracks'),
  addRepoTrack: (input: string, description = '') =>
    http.post('/tracks/repo', { input, description }),
  addKeywordTrack: (keyword: string, min_stars = 100) =>
    http.post('/tracks/keyword', { keyword, min_stars }),
  addTopicTrack: (topic: string, min_stars = 100, description = '') =>
    http.post('/tracks/topic', { topic, min_stars, description }),
  deleteTrack: (id: number) => http.delete(`/tracks/${id}`),
  toggleTrack: (id: number, is_active: boolean) =>
    http.patch(`/tracks/${id}`, null, { params: { is_active } }),
  updateTrackStars: (id: number, min_stars: number) =>
    http.patch(`/tracks/${id}`, null, { params: { min_stars } }),
}
