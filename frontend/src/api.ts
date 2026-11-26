const API_BASE = ''
import type {
  Account, AnalyticsOverview, AssetCapabilities, AuditEvent, Draft, MediaAsset, MetricSnapshot,
  MetricSnapshotInput, Preset, Preview, PublishTask, SchedulePlan, VideoConfig, VideoMetadata,
} from './types'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(data.detail || `请求失败（${response.status}）`)
  }
  return data as T
}

export const api = {
  health: () => request<{ status: string; publishing_enabled: boolean }>('/api/health'),
  presets: () => request<Preset[]>('/api/presets'),
  savePreset: (payload: { name: string; description: string; platform_hint: string; style: Preset['style'] }) =>
    request<Preset>('/api/presets', { method: 'POST', body: JSON.stringify(payload) }),
  updatePreset: (id: string, payload: { name: string; description: string; platform_hint: string; style: Preset['style'] }) =>
    request<Preset>(`/api/presets/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deletePreset: (id: string) => request<void>(`/api/presets/${id}`, { method: 'DELETE' }),
  reuseDraft: (id: number, targetPlatform: 'csdn' | 'zhihu', adapt: boolean) => request<Draft>(`/api/drafts/${id}/reuse`, {
    method: 'POST', body: JSON.stringify({ target_platform: targetPlatform, adapt }),
  }),
  drafts: () => request<Draft[]>('/api/drafts'),
  saveDraft: (draft: Draft) => request<Draft>(draft.id ? `/api/drafts/${draft.id}` : '/api/drafts', {
    method: draft.id ? 'PUT' : 'POST',
    body: JSON.stringify(draft),
  }),
  deleteDraft: (id: number) => request<void>(`/api/drafts/${id}`, { method: 'DELETE' }),
  generate: (payload: { topic: string; style: string; length: number; with_headings: boolean; with_tags: boolean }) =>
    request<{ title: string; body: string; tags: string[] }>('/api/generate', { method: 'POST', body: JSON.stringify(payload) }),
  preview: (payload: { title: string; body: string; preset_id: string; cover_url: string | null; tags?: string[]; style?: Preset['style'] }) =>
    request<Preview>('/api/preview', { method: 'POST', body: JSON.stringify(payload) }),
  cover: (title: string, background?: File | null) => {
    const form = new FormData()
    form.append('title', title)
    if (background) form.append('background', background)
    return fetch('/api/cover', { method: 'POST', body: form }).then(async (response) => {
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '封面生成失败')
      return data as { cover_url: string }
    })
  },
  videoConfig: () => request<VideoConfig>('/api/video/config'),
  uploadVideo: (file: File) => {
    const form = new FormData()
    form.append('video', file)
    return fetch('/api/videos', { method: 'POST', body: form }).then(async (response) => {
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '视频上传失败')
      return data as VideoMetadata
    })
  },
  transcodeVideo: (videoPath: string) => request<VideoMetadata>('/api/video/transcode', {
    method: 'POST', body: JSON.stringify({ video_path: videoPath }),
  }),
  videoCover: (videoPath: string, title: string, atSeconds?: number) => request<{ cover_url: string }>('/api/video/cover', {
    method: 'POST', body: JSON.stringify({ video_path: videoPath, title, at_seconds: atSeconds }),
  }),
  assets: (params: { kind?: 'image' | 'video'; tag?: string; q?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.kind) query.set('kind', params.kind)
    if (params.tag) query.set('tag', params.tag)
    if (params.q) query.set('q', params.q)
    return request<MediaAsset[]>(`/api/assets${query.size ? `?${query}` : ''}`)
  },
  assetCapabilities: () => request<AssetCapabilities>('/api/assets/capabilities'),
  uploadAsset: (file: File, tags: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('tags', tags)
    return fetch('/api/assets', { method: 'POST', body: form }).then(async (response) => {
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || '图片上传失败')
      return data as MediaAsset
    })
  },
  updateAsset: (id: number, tags: string[]) => request<MediaAsset>(`/api/assets/${id}`, {
    method: 'PATCH', body: JSON.stringify({ tags }),
  }),
  deleteAsset: (id: number) => request<void>(`/api/assets/${id}`, { method: 'DELETE' }),
  randomAsset: (kind: 'image' | 'video', tag?: string) => request<MediaAsset>(`/api/assets/random?kind=${kind}${tag ? `&tag=${encodeURIComponent(tag)}` : ''}`),
  generateAsset: (prompt: string, tags: string[]) => request<MediaAsset>('/api/assets/generate', {
    method: 'POST', body: JSON.stringify({ prompt, tags }),
  }),
  accounts: () => request<Account[]>('/api/accounts'),
  importCookies: (platform: string, nickname: string, cookieJson: string) => request<Account>('/api/accounts/cookies', {
    method: 'POST', body: JSON.stringify({ platform, nickname, cookie_json: cookieJson }),
  }),
  validateAccount: (id: number) => request<Account>(`/api/accounts/${id}/validate`, { method: 'POST' }),
  deleteAccount: (id: number) => request<void>(`/api/accounts/${id}`, { method: 'DELETE' }),
  tasks: (params: { status?: PublishTask['status']; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    if (params.limit) query.set('limit', String(params.limit))
    return request<PublishTask[]>(`/api/tasks${query.size ? `?${query}` : ''}`)
  },
  publish: (payload: {
    draft_id: number
    account_id: number
    preset_id: string
    authorized: boolean
    ad_acknowledged: boolean
    scheduled_at: string | null
    max_retries: number
    idempotency_key?: string
  }) => request<PublishTask>('/api/publish', { method: 'POST', body: JSON.stringify(payload) }),
  retry: (id: number) => request<PublishTask>(`/api/tasks/${id}/retry`, { method: 'POST' }),
  controlTask: (id: number, action: 'pause' | 'resume' | 'skip') =>
    request<PublishTask>(`/api/tasks/${id}/${action}`, { method: 'POST' }),
  schedules: () => request<SchedulePlan[]>('/api/schedules'),
  createSchedule: (payload: {
    name: string
    draft_id: number
    account_ids: number[]
    preset_id: string
    cron_expr: string | null
    scheduled_at: string | null
    authorized: boolean
  }) => request<SchedulePlan>('/api/schedules', { method: 'POST', body: JSON.stringify(payload) }),
  toggleSchedule: (id: number, enabled: boolean) =>
    request<SchedulePlan>(`/api/schedules/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
  deleteSchedule: (id: number) => request<void>(`/api/schedules/${id}`, { method: 'DELETE' }),
  analytics: (days = 30) => request<AnalyticsOverview>(`/api/analytics?days=${days}`),
  saveMetric: (payload: MetricSnapshotInput) => request<MetricSnapshot>('/api/metrics', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  auditEvents: (params: { outcome?: AuditEvent['outcome']; entityType?: string } = {}) => {
    const query = new URLSearchParams()
    if (params.outcome) query.set('outcome', params.outcome)
    if (params.entityType) query.set('entity_type', params.entityType)
    return request<AuditEvent[]>(`/api/audit${query.size ? `?${query}` : ''}`)
  },
}
