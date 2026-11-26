<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle, ArrowUpRight, BarChart3, BookOpenText, CalendarClock, Check, CheckCircle2, ChevronRight,
  CircleCheck, Clock3, ExternalLink, Feather, Film, FolderOpen, HardDrive, History,
  Image as ImageIcon, KeyRound, LayoutTemplate, LoaderCircle, LockKeyhole, Menu,
  Pause, Play, Plus, RefreshCw, Repeat2, RotateCcw, Save, Scissors, Send, ShieldCheck, SkipForward, Sparkles, Trash2, Upload,
  Video as VideoIcon, WandSparkles, X,
} from 'lucide-vue-next'
import { api } from './api'
import AnalyticsDashboard from './components/AnalyticsDashboard.vue'
import AuditTrail from './components/AuditTrail.vue'
import MediaLibrary from './components/MediaLibrary.vue'
import TemplateEditor from './components/TemplateEditor.vue'
import type { Account, Draft, Finding, MediaAsset, Preset, PublishTask, SchedulePlan, VideoConfig, VideoMetadata } from './types'

type View = 'editor' | 'video' | 'media' | 'records' | 'analytics' | 'accounts' | 'presets' | 'schedules'
type TaskAction = 'pause' | 'resume' | 'skip'

const BILIBILI_PARTITIONS = ['知识', '科技', '生活', '娱乐', '影视', '音乐', '游戏', '资讯', '美食', '时尚']

function emptyDraft(contentType: 'article' | 'video' = 'article'): Draft {
  return {
    title: '', body: '', source: 'manual', tags: [], cover_image: null, status: 'draft',
    content_type: contentType, video_path: null, video_duration: null, video_width: null,
    video_height: null, video_partition: contentType === 'video' ? '知识' : null, video_collection: null,
  }
}

const view = ref<View>('editor')
const mobileNavOpen = ref(false)
const presets = ref<Preset[]>([])
const selectedPreset = ref('fresh')
const accounts = ref<Account[]>([])
const selectedAccount = ref<number | null>(null)
const selectedVideoAccount = ref<number | null>(null)
const drafts = ref<Draft[]>([])
const draft = ref<Draft>(emptyDraft())
const videoDraft = ref<Draft>(emptyDraft('video'))
const previewHtml = ref('')
const findings = ref<Finding[]>([])
const stats = ref({ characters: 0, readingMinutes: 1 })
const previewLoading = ref(false)
const generating = ref(false)
const saving = ref(false)
const coverLoading = ref(false)
const publishing = ref(false)
const videoUploading = ref(false)
const videoProcessing = ref<'transcode' | 'cover' | null>(null)
const videoConfig = ref<VideoConfig | null>(null)
const videoSize = ref(0)
const videoFindings = ref<Finding[]>([])
const videoStats = ref({ characters: 0, readingMinutes: 1 })
const videoTagInput = ref('')
const videoInput = ref<HTMLInputElement | null>(null)
const coverAtSeconds = ref('1')
const videoScheduledAt = ref('')
const articleAuthorized = ref(false)
const videoAuthorized = ref(false)
const articleAdAcknowledged = ref(false)
const videoAdAcknowledged = ref(false)
const showPublishModal = ref(false)
const publishModal = ref<HTMLDivElement | null>(null)
let publishModalTrigger: HTMLElement | null = null
const showReuseModal = ref(false)
const reuseModal = ref<HTMLDivElement | null>(null)
let reuseModalTrigger: HTMLElement | null = null
const mobileMenuButton = ref<HTMLButtonElement | null>(null)
const navMedia = window.matchMedia('(max-width: 900px)')
const compactViewport = ref(navMedia.matches)
const templateEditor = ref<InstanceType<typeof TemplateEditor> | null>(null)
const reuseTarget = ref<'csdn' | 'zhihu'>('csdn')
const reuseAdapt = ref(false)
const reusing = ref(false)
const toast = ref('')
const serverOk = ref(false)
const publishingEnabled = ref(true)
const topic = ref('')
const promptStyle = ref('清晰、自然、有信息量')
const targetLength = ref(1200)
const tagInput = ref('')
const tasks = ref<PublishTask[]>([])
const expandedTask = ref<number | null>(null)
const nickname = ref('我的 CSDN')
const accountPlatform = ref('csdn')
const cookieJson = ref('')
const importing = ref(false)
const validatingId = ref<number | null>(null)
const scheduledAt = ref('')
const maxRetries = ref(1)
const schedules = ref<SchedulePlan[]>([])
const showScheduleForm = ref(false)
const scheduleSaving = ref(false)
const scheduleName = ref('')
const scheduleDraftId = ref<number | null>(null)
const scheduleAccountIds = ref<number[]>([])
const scheduleMode = ref<'once' | 'cron'>('once')
const scheduleAt = ref('')
const cronExpr = ref('30 9 * * *')
const scheduleAuthorized = ref(false)
const taskBusyId = ref<number | null>(null)
const bodyEditor = ref<HTMLTextAreaElement | null>(null)
const backgroundInput = ref<HTMLInputElement | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined
let articlePreviewTimer: ReturnType<typeof setTimeout> | undefined
let videoPreviewTimer: ReturnType<typeof setTimeout> | undefined
let articlePreviewRequest = 0
let videoComplianceRequest = 0
let videoUploadRequest = 0
let articleIdempotencyKey = ''
let videoIdempotencyKey = ''
let articleBaseline = JSON.stringify(draft.value)
let videoBaseline = JSON.stringify(videoDraft.value)

const activePreset = computed(() => presets.value.find((item) => item.id === selectedPreset.value))
const activeAccount = computed(() => accounts.value.find((item) => item.id === selectedAccount.value))
const activeVideoAccount = computed(() => accounts.value.find((item) => item.id === selectedVideoAccount.value))
const articleDrafts = computed(() => drafts.value.filter((item) => item.content_type !== 'video'))
const videoDrafts = computed(() => drafts.value.filter((item) => item.content_type === 'video'))
const adFindings = computed(() => findings.value.filter((item) => item.type !== 'links'))
const blocked = computed(() => findings.value.some((item) => item.type === 'prohibited'))
const videoAdFindings = computed(() => videoFindings.value.filter((item) => item.type !== 'links'))
const videoBlocked = computed(() => videoFindings.value.some((item) => item.type === 'prohibited'))
const runningTasks = computed(() => tasks.value.filter((task) => task.status === 'pending' || task.status === 'running'))
const successfulTasks = computed(() => tasks.value.filter((task) => task.status === 'success').length)
const activeSchedules = computed(() => schedules.value.filter((plan) => plan.enabled).length)
const videoPreviewUrl = computed(() => videoDraft.value.video_path ? `/${videoDraft.value.video_path}` : '')
const videoDurationLabel = computed(() => formatDuration(videoDraft.value.video_duration || 0))
const videoFileLabel = computed(() => videoDraft.value.video_path?.split('/').pop() || '尚未选择视频')
const videoReady = computed(() => Boolean(videoDraft.value.title.trim() && videoDraft.value.video_path))
const articleDirty = computed(() => JSON.stringify(draft.value) !== articleBaseline)
const videoDirty = computed(() => JSON.stringify(videoDraft.value) !== videoBaseline)
const scheduleDraft = computed(() => drafts.value.find((item) => item.id === scheduleDraftId.value))
const scheduleAccounts = computed(() => accounts.value.filter((account) => (
  scheduleDraft.value?.content_type === 'video' ? account.platform === 'bilibili' : account.platform !== 'bilibili'
)))
const modalDraft = computed(() => view.value === 'video' ? videoDraft.value : draft.value)
const modalAccount = computed(() => view.value === 'video' ? activeVideoAccount.value : activeAccount.value)
const modalScheduledAt = computed(() => view.value === 'video' ? videoScheduledAt.value : scheduledAt.value)
const pageTitle = computed(() => ({
  editor: '内容编辑台', video: '视频发布', media: '素材库', records: '发布记录', analytics: '数据看板', accounts: '账号与授权', presets: '模板工坊', schedules: '定时与队列',
})[view.value])
const today = computed(() => new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date()))

function platformLabel(platform: string) {
  return ({ csdn: 'CSDN', zhihu: '知乎', bilibili: '哔哩哔哩' })[platform] || platform
}

function platformInitial(platform: string) {
  return ({ csdn: 'C', zhihu: '知', bilibili: 'B' })[platform] || platform.slice(0, 1).toUpperCase()
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function formatBytes(bytes: number) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function localDateTimeValue(date: Date) {
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function toScheduledIso(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) throw new Error('请选择有效的定时时间')
  return date.toISOString()
}

function notify(message: string) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 4200)
}

function trapModalFocus(event: KeyboardEvent, modal: HTMLElement | null) {
  if (event.key !== 'Tab' || !modal) return
  const focusable = Array.from(modal.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.offsetParent !== null)
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (!first || !last) return
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(showPublishModal, async (open) => {
  if (open) {
    publishModalTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    publishModal.value?.querySelector<HTMLButtonElement>('button')?.focus()
  } else {
    publishModalTrigger?.focus()
    publishModalTrigger = null
  }
})

watch(showReuseModal, async (open) => {
  if (open) {
    reuseModalTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    reuseModal.value?.querySelector<HTMLButtonElement>('button')?.focus()
  } else {
    reuseModalTrigger?.focus()
    reuseModalTrigger = null
  }
})

watch(mobileNavOpen, async (open) => {
  if (open) {
    await nextTick()
    document.querySelector<HTMLButtonElement>('.sidebar.is-open .main-nav button')?.focus()
  } else if (compactViewport.value) {
    mobileMenuButton.value?.focus()
  }
})

function handlePublishModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !publishing.value) {
    showPublishModal.value = false
    return
  }
  trapModalFocus(event, publishModal.value)
}

function handleReuseModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && !reusing.value) {
    showReuseModal.value = false
    return
  }
  trapModalFocus(event, reuseModal.value)
}

function closeReuseModal() {
  if (!reusing.value) showReuseModal.value = false
}

function changeView(next: View) {
  if (view.value === 'presets' && next !== 'presets' && !templateEditor.value?.canLeave()) {
    if (!window.confirm('模板还有未保存的修改，确定离开吗？')) return
  }
  view.value = next
  mobileNavOpen.value = false
  if (next === 'records') void loadTasks()
  if (next === 'schedules') void loadSchedules()
  if (next === 'video') void updateVideoCompliance()
}

async function loadInitialData() {
  const [health, presetResult, accountResult, draftResult, taskResult, videoResult] = await Promise.allSettled([
    api.health(), api.presets(), api.accounts(), api.drafts(), api.tasks(), api.videoConfig(),
  ])
  if (health.status === 'fulfilled') {
    serverOk.value = health.value.status === 'ok'
    publishingEnabled.value = health.value.publishing_enabled
  } else notify('本地服务连接失败，请检查后端是否启动')
  if (presetResult.status === 'fulfilled') presets.value = presetResult.value
  if (accountResult.status === 'fulfilled') accounts.value = accountResult.value
  if (draftResult.status === 'fulfilled') drafts.value = draftResult.value
  if (taskResult.status === 'fulfilled') tasks.value = taskResult.value
  if (videoResult.status === 'fulfilled') videoConfig.value = videoResult.value
  for (const result of [presetResult, accountResult, draftResult, taskResult, videoResult]) {
    if (result.status === 'rejected') notify(result.reason instanceof Error ? result.reason.message : '部分数据加载失败')
  }
  const articles = drafts.value.filter((item) => item.content_type !== 'video')
  const videos = drafts.value.filter((item) => item.content_type === 'video')
  selectedAccount.value = accounts.value.find((item) => item.platform !== 'bilibili')?.id ?? null
  selectedVideoAccount.value = accounts.value.find((item) => item.platform === 'bilibili')?.id ?? null
  scheduleDraftId.value = articles[0]?.id ?? videos[0]?.id ?? null
  if (!scheduleAt.value) scheduleAt.value = localDateTimeValue(new Date(Date.now() + 10 * 60000))
  if (articles[0]) loadDraft(articles[0])
  if (videos[0]) loadVideoDraft(videos[0])
}

function confirmDiscard() {
  return !articleDirty.value && !videoDirty.value || window.confirm('当前文章或视频有未保存的修改，确定丢弃吗？')
}

function loadDraft(item: Draft) {
  if (draft.value.id === item.id || !confirmDiscard()) return
  articleBaseline = JSON.stringify(item)
  articleIdempotencyKey = ''
  draft.value = { ...item, tags: [...item.tags] }
  tagInput.value = item.tags.join('，')
  articleAuthorized.value = false
  void updatePreview()
}

function loadVideoDraft(item: Draft) {
  if (videoDraft.value.id === item.id || !confirmDiscard()) return
  videoBaseline = JSON.stringify(item)
  videoUploadRequest += 1
  videoUploading.value = false
  videoIdempotencyKey = ''
  videoDraft.value = { ...item, tags: [...item.tags] }
  videoTagInput.value = item.tags.join('，')
  videoSize.value = 0
  videoAuthorized.value = false
  void updateVideoCompliance()
}

function newVideoDraft() {
  if (!confirmDiscard()) return
  const blank = emptyDraft('video')
  videoBaseline = JSON.stringify(blank)
  videoUploadRequest += 1
  videoUploading.value = false
  videoIdempotencyKey = ''
  videoDraft.value = emptyDraft('video')
  videoTagInput.value = ''
  videoSize.value = 0
  videoFindings.value = []
  videoStats.value = { characters: 0, readingMinutes: 1 }
  videoAuthorized.value = false
}

function draftSnapshot(value: Draft): Draft {
  return JSON.parse(JSON.stringify(value)) as Draft
}

function mergeSavedDraft(current: Draft, snapshot: Draft, saved: Draft): Draft {
  if (JSON.stringify(current) === JSON.stringify(snapshot)) return { ...saved, tags: [...saved.tags] }
  return {
    ...current,
    id: saved.id,
    status: saved.status,
    created_at: saved.created_at,
    updated_at: saved.updated_at,
  }
}

async function persistDraft(current: Draft) {
  const snapshot = draftSnapshot(current)
  const saved = await api.saveDraft(snapshot)
  drafts.value = await api.drafts().catch(() => drafts.value)
  return { saved, snapshot }
}

async function saveDraft() {
  if (saving.value || publishing.value) return
  if (!draft.value.title.trim()) {
    notify('先给这篇内容起一个标题')
    return
  }
  saving.value = true
  try {
    const { saved, snapshot } = await persistDraft(draft.value)
    draft.value = mergeSavedDraft(draft.value, snapshot, saved)
    articleBaseline = JSON.stringify(draft.value)
    notify('草稿已安全保存到本机')
  } catch (error) {
    notify(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function prepareReuse() {
  if (!draft.value.title.trim() || !draft.value.body.trim()) {
    notify('请先填写标题和正文，再创建复用版本')
    return
  }
  if (!draft.value.id) {
    await saveDraft()
    if (!draft.value.id) return
  }
  reuseTarget.value = activeAccount.value?.platform === 'zhihu' ? 'zhihu' : 'csdn'
  reuseAdapt.value = false
  showReuseModal.value = true
}

async function confirmReuse() {
  if (!draft.value.id || reusing.value) return
  reusing.value = true
  try {
    const reused = await api.reuseDraft(draft.value.id, reuseTarget.value, reuseAdapt.value)
    drafts.value = await api.drafts()
    showReuseModal.value = false
    selectedAccount.value = accounts.value.find((account) => account.platform === reuseTarget.value)?.id ?? selectedAccount.value
    loadDraft(reused)
    notify(reuseAdapt.value
      ? `${platformLabel(reuseTarget.value)} 适配版本已创建，请核对事实后再发布`
      : '独立复用版本已创建，原稿保持不变')
  } catch (error) {
    notify(error instanceof Error ? error.message : '复用版本创建失败')
  } finally {
    reusing.value = false
  }
}

async function saveVideoDraft() {
  if (saving.value || publishing.value) return
  if (!videoDraft.value.title.trim()) {
    notify('先给视频起一个标题')
    return
  }
  saving.value = true
  try {
    const { saved, snapshot } = await persistDraft(videoDraft.value)
    videoDraft.value = mergeSavedDraft(videoDraft.value, snapshot, saved)
    videoBaseline = JSON.stringify(videoDraft.value)
    notify('视频草稿已保存到本机')
  } catch (error) {
    notify(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function applyVideoMetadata(metadata: VideoMetadata) {
  videoDraft.value.video_path = metadata.video_path
  videoDraft.value.video_duration = metadata.duration
  videoDraft.value.video_width = metadata.width
  videoDraft.value.video_height = metadata.height
  videoSize.value = metadata.size_bytes
}

function useMediaImage(asset: MediaAsset) {
  draft.value.cover_image = asset.url
  articleAuthorized.value = false
  changeView('editor')
  notify(`已将「${asset.original_name}」设为文章封面`)
}

function useMediaVideo(asset: MediaAsset) {
  videoDraft.value.video_path = asset.stored_path
  videoDraft.value.video_duration = asset.duration
  videoDraft.value.video_width = asset.width
  videoDraft.value.video_height = asset.height
  videoSize.value = asset.size_bytes
  videoAuthorized.value = false
  changeView('video')
  notify(`已载入视频「${asset.original_name}」，保存后即可投稿`)
}

async function updateVideoCompliance() {
  const requestId = ++videoComplianceRequest
  if (!videoDraft.value.title && !videoDraft.value.body) {
    videoFindings.value = []
    videoStats.value = { characters: 0, readingMinutes: 1 }
    return
  }
  try {
    const preview = await api.preview({
      title: videoDraft.value.title,
      body: videoDraft.value.body,
      preset_id: 'fresh',
      cover_url: videoDraft.value.cover_image,
      tags: videoDraft.value.tags,
    })
    if (requestId !== videoComplianceRequest) return
    videoFindings.value = preview.findings
    videoStats.value = preview.stats
  } catch (error) {
    if (requestId === videoComplianceRequest) notify(error instanceof Error ? error.message : '视频文案检查失败')
  }
}

async function processVideoFile(file: File) {
  if (videoUploading.value || publishing.value) return
  if (videoConfig.value && file.size > videoConfig.value.max_upload_mb * 1024 * 1024) {
    notify(`视频不能超过 ${videoConfig.value.max_upload_mb} MB`)
    return
  }
  const requestId = ++videoUploadRequest
  const draftId = videoDraft.value.id ?? null
  videoUploading.value = true
  try {
    const metadata = await api.uploadVideo(file)
    if (requestId !== videoUploadRequest || draftId !== (videoDraft.value.id ?? null)) return
    applyVideoMetadata(metadata)
    notify('视频已上传并通过时长与画面校验')
  } catch (error) {
    if (requestId === videoUploadRequest) notify(error instanceof Error ? error.message : '视频上传失败')
  } finally {
    if (requestId === videoUploadRequest) videoUploading.value = false
  }
}

async function uploadVideoFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await processVideoFile(file)
  input.value = ''
}

function dropVideoFile(event: DragEvent) {
  const file = event.dataTransfer?.files?.[0]
  if (file) void processVideoFile(file)
}

async function transcodeVideoFile() {
  if (videoProcessing.value || publishing.value) return
  if (!videoDraft.value.video_path) {
    notify('请先上传视频')
    return
  }
  const videoPath = videoDraft.value.video_path
  videoProcessing.value = 'transcode'
  try {
    const metadata = await api.transcodeVideo(videoPath)
    if (videoDraft.value.video_path !== videoPath) return
    applyVideoMetadata(metadata)
    notify('已转为 H.264 / AAC MP4，并启用快速播放')
  } catch (error) {
    notify(error instanceof Error ? error.message : '视频转码失败')
  } finally {
    videoProcessing.value = null
  }
}

async function extractVideoCover() {
  if (videoProcessing.value || publishing.value) return
  if (!videoDraft.value.video_path || !videoDraft.value.title.trim()) {
    notify('请先上传视频并填写标题')
    return
  }
  const videoPath = videoDraft.value.video_path
  const title = videoDraft.value.title
  videoProcessing.value = 'cover'
  try {
    const at = coverAtSeconds.value === '' ? undefined : Number(coverAtSeconds.value)
    const result = await api.videoCover(videoPath, title, at)
    if (videoDraft.value.video_path !== videoPath || videoDraft.value.title !== title) return
    videoDraft.value.cover_image = result.cover_url
    notify('已从视频抽帧并合成封面')
  } catch (error) {
    notify(error instanceof Error ? error.message : '视频封面生成失败')
  } finally {
    videoProcessing.value = null
  }
}

function updateVideoTags() {
  videoDraft.value.tags = videoTagInput.value.split(/[,，]/).map((tag) => tag.trim().replace(/^#/, '')).filter(Boolean).slice(0, 10)
}

async function updatePreview() {
  const requestId = ++articlePreviewRequest
  if (!draft.value.title && !draft.value.body) {
    previewHtml.value = ''
    findings.value = []
    stats.value = { characters: 0, readingMinutes: 1 }
    previewLoading.value = false
    return
  }
  previewLoading.value = true
  try {
    const preview = await api.preview({
      title: draft.value.title,
      body: draft.value.body,
      preset_id: selectedPreset.value,
      cover_url: draft.value.cover_image,
      tags: draft.value.tags,
    })
    if (requestId !== articlePreviewRequest) return
    previewHtml.value = preview.html
    findings.value = preview.findings
    stats.value = preview.stats
  } catch (error) {
    if (requestId === articlePreviewRequest) notify(error instanceof Error ? error.message : '预览生成失败')
  } finally {
    if (requestId === articlePreviewRequest) previewLoading.value = false
  }
}

watch(
  [() => draft.value.id, () => draft.value.title, () => draft.value.body, () => draft.value.tags, () => draft.value.cover_image, selectedPreset],
  () => {
    clearTimeout(articlePreviewTimer)
    articlePreviewTimer = setTimeout(updatePreview, 420)
  },
)

watch(
  [() => videoDraft.value.id, () => videoDraft.value.title, () => videoDraft.value.body, () => videoDraft.value.tags, () => videoDraft.value.cover_image],
  () => {
    clearTimeout(videoPreviewTimer)
    videoPreviewTimer = setTimeout(updateVideoCompliance, 420)
  },
)

watch(
  [
    () => draft.value.title, () => draft.value.body, () => draft.value.tags.join(','),
    () => draft.value.cover_image, selectedPreset, selectedAccount,
  ],
  () => {
    articleAuthorized.value = false
    articleAdAcknowledged.value = false
    articleIdempotencyKey = ''
  },
)

watch(
  [
    () => videoDraft.value.title, () => videoDraft.value.body,
    () => videoDraft.value.tags.join(','), () => videoDraft.value.video_path, () => videoDraft.value.video_duration,
    () => videoDraft.value.video_width, () => videoDraft.value.video_height,
    () => videoDraft.value.video_partition, () => videoDraft.value.video_collection,
    () => videoDraft.value.cover_image, selectedVideoAccount,
  ],
  () => {
    videoAuthorized.value = false
    videoAdAcknowledged.value = false
    videoIdempotencyKey = ''
  },
)

function useExample() {
  if (!confirmDiscard()) return
  const example: Draft = {
    id: undefined,
    title: '把复杂的事，交给清晰的系统',
    body: `好的工具不应该抢走注意力，而应该让人更专注于真正重要的事情。

## 从一个真实问题开始

内容发布看似只是点击几个按钮，实际上却牵涉账号、排版、时间与平台规则。真正可靠的工作台，应当把这些细节收进一套清晰的流程。

> 发布是主角，编辑是配角。

## 让每一次操作都有回响

从草稿到预览，再到发布记录，每一步都应该可见、可追踪。失败时说明原因，成功时保留链接，不把不确定性留给用户。

## 留给创作者的空间

当系统处理好重复劳动，创作者才能把时间留给观点、故事与表达。这正是 PublishFlow 想做的事。`,
    source: 'manual',
    tags: ['效率工具', '内容创作', '工作流'],
    cover_image: null,
    content_type: 'article',
    video_path: null,
    video_duration: null,
    video_width: null,
    video_height: null,
    video_partition: null,
    video_collection: null,
    status: 'draft',
  }
  articleBaseline = JSON.stringify(example)
  draft.value = example
  tagInput.value = '效率工具，内容创作，工作流'
  void updatePreview()
  notify('已填入示例内容，可以直接体验排版与封面')
}

async function generateArticle() {
  if (articleDirty.value && !confirmDiscard()) return
  if (topic.value.trim().length < 2) {
    notify('先写下文章主题或关键词')
    return
  }
  generating.value = true
  try {
    const result = await api.generate({
      topic: topic.value.trim(), style: promptStyle.value, length: targetLength.value,
      with_headings: true, with_tags: true,
    })
    draft.value = { ...draft.value, id: undefined, title: result.title, body: result.body, tags: result.tags, source: 'ai', status: 'draft' }
    articleBaseline = JSON.stringify(draft.value)
    tagInput.value = result.tags.join('，')
    notify('文章已生成，请核对事实后再发布')
  } catch (error) {
    notify(error instanceof Error ? error.message : '生成失败')
  } finally {
    generating.value = false
  }
}

function applyFormat(prefix: string, suffix = prefix) {
  const textarea = bodyEditor.value
  if (!textarea) return
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const selected = draft.value.body.slice(start, end) || '文字'
  draft.value.body = draft.value.body.slice(0, start) + prefix + selected + suffix + draft.value.body.slice(end)
  requestAnimationFrame(() => {
    textarea.focus()
    textarea.setSelectionRange(start + prefix.length, start + prefix.length + selected.length)
  })
}

function updateTags() {
  draft.value.tags = tagInput.value.split(/[,，]/).map((tag) => tag.trim().replace(/^#/, '')).filter(Boolean).slice(0, 8)
}

async function generateCover() {
  if (!draft.value.title.trim()) {
    notify('先填写标题，再生成封面')
    return
  }
  coverLoading.value = true
  try {
    const result = await api.cover(draft.value.title)
    draft.value.cover_image = result.cover_url
    notify('封面已生成并保存到本机')
  } catch (error) {
    notify(error instanceof Error ? error.message : '封面生成失败')
  } finally {
    coverLoading.value = false
  }
}

async function uploadBackground(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!draft.value.title.trim()) {
    notify('先填写标题，再合成封面')
    return
  }
  coverLoading.value = true
  try {
    const result = await api.cover(draft.value.title, file)
    draft.value.cover_image = result.cover_url
    notify('已用你的图片合成新封面')
  } catch (error) {
    notify(error instanceof Error ? error.message : '封面上传失败')
  } finally {
    coverLoading.value = false
    if (backgroundInput.value) backgroundInput.value.value = ''
  }
}

async function saveBeforePublish() {
  const { saved, snapshot } = await persistDraft(draft.value)
  draft.value = mergeSavedDraft(draft.value, snapshot, saved)
  articleBaseline = JSON.stringify({ ...snapshot, id: saved.id, status: saved.status, created_at: saved.created_at, updated_at: saved.updated_at })
  return saved
}

function preparePublish() {
  if (!publishingEnabled.value) {
    notify('当前运行模式已禁用真实发布，请使用带可见浏览器的本机模式')
    return
  }
  if (publishing.value) return
  if (blocked.value) {
    notify('内容包含禁止发布项，请先修改')
    return
  }
  if (adFindings.value.length && !articleAdAcknowledged.value) {
    notify('请先确认广告法风险用语')
    return
  }
  if (!articleAuthorized.value) {
    notify('请先确认内容归属与平台授权')
    return
  }
  if (!activeAccount.value) {
    notify('请先导入 CSDN 或知乎账号')
    changeView('accounts')
    return
  }
  if (!activeAccount.value.login_valid) {
    notify('该账号登录态尚未验证，请先在账号页验证')
    return
  }
  articleIdempotencyKey ||= createIdempotencyKey('article')
  showPublishModal.value = true
}

async function confirmPublish() {
  if (publishing.value) return
  publishing.value = true
  try {
    const scheduledValue = toScheduledIso(scheduledAt.value)
    const saved = await saveBeforePublish()
    if (!saved.id || !selectedAccount.value) throw new Error('草稿或账号信息不完整')
    const task = await api.publish({
      draft_id: saved.id,
      account_id: selectedAccount.value,
      preset_id: selectedPreset.value,
      authorized: articleAuthorized.value,
      ad_acknowledged: articleAdAcknowledged.value,
      scheduled_at: scheduledValue,
      max_retries: maxRetries.value,
      idempotency_key: articleIdempotencyKey,
    })
    showPublishModal.value = false
    articleAuthorized.value = false
    articleIdempotencyKey = ''
    notify(scheduledAt.value
      ? `已创建 ${platformLabel(task.platform)} 定时发布任务`
      : `发布任务已提交，正在打开 ${platformLabel(task.platform)} 浏览器`)
    await loadTasks()
    expandedTask.value = task.id
  } catch (error) {
    notify(error instanceof Error ? error.message : '发布失败')
  } finally {
    publishing.value = false
  }
}

async function saveBeforeVideoPublish() {
  const { saved, snapshot } = await persistDraft(videoDraft.value)
  videoDraft.value = mergeSavedDraft(videoDraft.value, snapshot, saved)
  videoBaseline = JSON.stringify({ ...snapshot, id: saved.id, status: saved.status, created_at: saved.created_at, updated_at: saved.updated_at })
  return saved
}

function prepareVideoPublish() {
  if (!publishingEnabled.value) {
    notify('当前运行模式已禁用真实发布，请使用带可见浏览器的本机模式')
    return
  }
  if (publishing.value) return
  if (!videoReady.value) {
    notify('请先填写标题并上传视频')
    return
  }
  if (videoBlocked.value) {
    notify('视频标题或简介包含禁止发布项，请先修改')
    return
  }
  if (videoAdFindings.value.length && !videoAdAcknowledged.value) {
    notify('请先确认广告法风险用语')
    return
  }
  if (!videoAuthorized.value) {
    notify('请先确认内容归属与平台授权')
    return
  }
  if (!activeVideoAccount.value) {
    notify('请先导入哔哩哔哩账号')
    changeView('accounts')
    return
  }
  if (!activeVideoAccount.value.login_valid) {
    notify('该账号登录态尚未验证，请先在账号页验证')
    return
  }
  videoIdempotencyKey ||= createIdempotencyKey('video')
  showPublishModal.value = true
}

async function confirmVideoPublish() {
  if (publishing.value) return
  publishing.value = true
  try {
    const scheduledValue = toScheduledIso(videoScheduledAt.value)
    const saved = await saveBeforeVideoPublish()
    if (!saved.id || !selectedVideoAccount.value) throw new Error('草稿或账号信息不完整')
    const task = await api.publish({
      draft_id: saved.id,
      account_id: selectedVideoAccount.value,
      preset_id: selectedPreset.value,
      authorized: videoAuthorized.value,
      ad_acknowledged: videoAdAcknowledged.value,
      scheduled_at: scheduledValue,
      max_retries: maxRetries.value,
      idempotency_key: videoIdempotencyKey,
    })
    showPublishModal.value = false
    videoAuthorized.value = false
    videoIdempotencyKey = ''
    notify(videoScheduledAt.value ? '已创建 B 站定时投稿任务' : '视频投稿任务已提交，正在打开本机浏览器')
    await loadTasks()
    expandedTask.value = task.id
  } catch (error) {
    notify(error instanceof Error ? error.message : '视频发布失败')
  } finally {
    publishing.value = false
  }
}

async function loadTasks() {
  try {
    tasks.value = await api.tasks()
  } catch (error) {
    notify(error instanceof Error ? error.message : '发布记录加载失败')
  }
}

async function retryTask(task: PublishTask) {
  try {
    await api.retry(task.id)
    notify('已重新提交发布任务')
    await loadTasks()
  } catch (error) {
    notify(error instanceof Error ? error.message : '无法重试')
  }
}

async function controlTask(task: PublishTask, action: TaskAction) {
  taskBusyId.value = task.id
  try {
    await api.controlTask(task.id, action)
    notify(({ pause: '任务已暂停', resume: '任务已恢复', skip: '任务已跳过' })[action])
    await loadTasks()
  } catch (error) {
    notify(error instanceof Error ? error.message : '队列操作失败')
  } finally {
    taskBusyId.value = null
  }
}

async function importAccount() {
  importing.value = true
  try {
    await api.importCookies(accountPlatform.value, nickname.value.trim() || `我的${platformLabel(accountPlatform.value)}`, cookieJson.value)
    accounts.value = await api.accounts()
    const imported = accounts.value.find((item) => item.platform === accountPlatform.value)
    if (accountPlatform.value === 'bilibili') selectedVideoAccount.value = imported?.id ?? selectedVideoAccount.value
    else selectedAccount.value = imported?.id ?? selectedAccount.value
    cookieJson.value = ''
    notify('Cookie 已加密保存，账号凭证不会发送到第三方')
  } catch (error) {
    notify(error instanceof Error ? error.message : 'Cookie 导入失败')
  } finally {
    importing.value = false
  }
}

function changeImportPlatform() {
  nickname.value = `我的${platformLabel(accountPlatform.value)}`
}

async function validateAccount(account: Account) {
  validatingId.value = account.id
  try {
    const updated = await api.validateAccount(account.id)
    accounts.value = accounts.value.map((item) => item.id === account.id ? updated : item)
    notify(updated.message || '登录态验证完成')
  } catch (error) {
    notify(error instanceof Error ? error.message : '验证失败')
  } finally {
    validatingId.value = null
  }
}

async function removeAccount(account: Account) {
  if (!window.confirm(`确定删除「${account.nickname}」的本地登录凭证吗？`)) return
  try {
    await api.deleteAccount(account.id)
    accounts.value = await api.accounts()
    scheduleAccountIds.value = scheduleAccountIds.value.filter((id) => id !== account.id)
    if (selectedAccount.value === account.id) selectedAccount.value = accounts.value.find((item) => item.platform !== 'bilibili')?.id ?? null
    if (selectedVideoAccount.value === account.id) selectedVideoAccount.value = accounts.value.find((item) => item.platform === 'bilibili')?.id ?? null
    notify('本地账号凭证已删除')
  } catch (error) {
    notify(error instanceof Error ? error.message : '删除失败')
  }
}

async function loadSchedules() {
  try {
    schedules.value = await api.schedules()
  } catch (error) {
    notify(error instanceof Error ? error.message : '调度计划加载失败')
  }
}

function openScheduleForm() {
  if (!publishingEnabled.value) {
    notify('当前运行模式已禁用真实发布，不能创建调度计划')
    return
  }
  const current = view.value === 'video' ? videoDraft.value : draft.value
  scheduleDraftId.value = current.id ?? (view.value === 'video' ? videoDrafts.value[0]?.id : articleDrafts.value[0]?.id) ?? null
  scheduleName.value = current.title ? `${current.title} · 发布计划` : ''
  scheduleAuthorized.value = false
  showScheduleForm.value = true
}

watch(scheduleDraftId, () => {
  const allowed = new Set(scheduleAccounts.value.map((account) => account.id))
  scheduleAccountIds.value = scheduleAccountIds.value.filter((id) => allowed.has(id))
})

function toggleScheduleAccount(accountId: number) {
  scheduleAccountIds.value = scheduleAccountIds.value.includes(accountId)
    ? scheduleAccountIds.value.filter((id) => id !== accountId)
    : [...scheduleAccountIds.value, accountId]
}

async function createSchedule() {
  if (!scheduleDraftId.value || !scheduleAccountIds.value.length) {
    notify('请选择草稿和至少一个发布账号')
    return
  }
  if (!scheduleName.value.trim()) {
    notify('请为调度计划起一个名字')
    return
  }
  if (!scheduleAuthorized.value) {
    notify('请确认内容归属与平台自动化授权')
    return
  }
  if (scheduleMode.value === 'once' && !scheduleAt.value) {
    notify('请选择一次性计划的执行时间')
    return
  }
  scheduleSaving.value = true
  try {
    const scheduledValue = scheduleMode.value === 'once' ? toScheduledIso(scheduleAt.value) : null
    await api.createSchedule({
      name: scheduleName.value.trim(),
      draft_id: scheduleDraftId.value,
      account_ids: scheduleAccountIds.value,
      preset_id: selectedPreset.value,
      cron_expr: scheduleMode.value === 'cron' ? cronExpr.value.trim() : null,
      scheduled_at: scheduledValue,
      authorized: scheduleAuthorized.value,
    })
    showScheduleForm.value = false
    scheduleAuthorized.value = false
    notify('调度计划已创建，任务会按账号顺序错峰执行')
    await loadSchedules()
  } catch (error) {
    notify(error instanceof Error ? error.message : '调度计划创建失败')
  } finally {
    scheduleSaving.value = false
  }
}

async function toggleSchedule(plan: SchedulePlan) {
  try {
    await api.toggleSchedule(plan.id, !plan.enabled)
    notify(plan.enabled ? '调度计划已暂停' : '调度计划已启用')
    await loadSchedules()
  } catch (error) {
    notify(error instanceof Error ? error.message : '计划状态更新失败')
  }
}

async function removeSchedule(plan: SchedulePlan) {
  if (!window.confirm(`确定删除调度计划「${plan.name}」吗？已生成的任务不会被删除。`)) return
  try {
    await api.deleteSchedule(plan.id)
    notify('调度计划已删除')
    await loadSchedules()
  } catch (error) {
    notify(error instanceof Error ? error.message : '计划删除失败')
  }
}

async function reloadPresets() {
  try {
    presets.value = await api.presets()
    if (!presets.value.some((preset) => preset.id === selectedPreset.value)) {
      selectedPreset.value = presets.value[0]?.id ?? ''
    }
  } catch (error) {
    notify(error instanceof Error ? error.message : '模板列表刷新失败')
  }
}

function selectPreset(preset: Preset) {
  selectedPreset.value = preset.id
  changeView('editor')
  notify(`已应用「${preset.name}」排版预设`)
}

function createIdempotencyKey(kind: 'article' | 'video') {
  const random = typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) => value.toString(16).padStart(2, '0')).join('')
  return `${kind}-${random}`
}

function manualRetryBlocked(task: PublishTask) {
  return task.submission_uncertain || ['未收到平台成功回执', '验证', '结果不确定'].some((marker) => (task.error_msg || '').includes(marker))
}

function statusLabel(status: string) {
  return ({ pending: '等待中', running: '发布中', success: '已发布', failed: '需处理', paused: '已暂停', skipped: '已跳过' })[status] || status
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!articleDirty.value && !videoDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (view.value === 'editor') void saveDraft()
    if (view.value === 'video') void saveVideoDraft()
  }
  if (event.key === 'Escape' && mobileNavOpen.value) mobileNavOpen.value = false
}

function handleViewportChange() {
  compactViewport.value = navMedia.matches
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  navMedia.addEventListener('change', handleViewportChange)
  void loadInitialData()
  pollTimer = setInterval(() => {
    if (runningTasks.value.length) void loadTasks()
  }, 3000)
  window.addEventListener('keydown', handleGlobalKeydown)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  navMedia.removeEventListener('change', handleViewportChange)
  window.removeEventListener('keydown', handleGlobalKeydown)
  clearTimeout(toastTimer)
  clearTimeout(articlePreviewTimer)
  clearTimeout(videoPreviewTimer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="app-shell">
    <aside id="workspace-sidebar" class="sidebar" :class="{ 'is-open': mobileNavOpen }" :inert="compactViewport && !mobileNavOpen">
      <button class="brand" aria-label="PublishFlow 首页" @click="changeView('editor')">
        <span class="brand-mark">P<span>F</span></span>
        <span class="brand-copy"><strong>PublishFlow</strong><small>本地发布工作台</small></span>
      </button>

      <div class="sidebar-label">工作空间</div>
      <nav class="main-nav" aria-label="主导航">
        <button :class="{ active: view === 'editor' }" @click="changeView('editor')"><Feather :size="18" /><span>内容编辑台</span><span class="nav-number" aria-hidden="true">01</span></button>
        <button :class="{ active: view === 'video' }" @click="changeView('video')"><VideoIcon :size="18" /><span>视频发布</span><span class="nav-number" aria-hidden="true">02</span></button>
        <button :class="{ active: view === 'media' }" @click="changeView('media')"><ImageIcon :size="18" /><span>素材库</span><span class="nav-number" aria-hidden="true">03</span></button>
        <button :class="{ active: view === 'records' }" @click="changeView('records')"><History :size="18" /><span>发布记录</span><span class="nav-number" aria-hidden="true">04</span></button>
        <button :class="{ active: view === 'analytics' }" @click="changeView('analytics')"><BarChart3 :size="18" /><span>数据看板</span><span class="nav-number" aria-hidden="true">05</span></button>
        <button :class="{ active: view === 'accounts' }" @click="changeView('accounts')"><KeyRound :size="18" /><span>账号与授权</span><span class="nav-number" aria-hidden="true">06</span></button>
        <button :class="{ active: view === 'presets' }" @click="changeView('presets')"><LayoutTemplate :size="18" /><span>模板工坊</span><span class="nav-number" aria-hidden="true">07</span></button>
        <button :class="{ active: view === 'schedules' }" @click="changeView('schedules')"><CalendarClock :size="18" /><span>定时与队列</span><span class="nav-number" aria-hidden="true">08</span></button>
      </nav>

      <div class="sidebar-spacer" />
      <div class="local-card">
        <div class="local-card-head"><span class="status-dot" :class="{ offline: !serverOk }"></span><strong>{{ serverOk ? '本地服务已连接' : '正在连接本地服务' }}</strong></div>
        <p>内容、凭证与记录<br />只保存在这台电脑。</p>
        <div class="local-card-foot"><HardDrive :size="13" /> SQLite · 本机存储</div>
      </div>
      <div class="sidebar-foot"><ShieldCheck :size="15" /><span>合规发布 · 完整审计</span><span>v0.5</span></div>
    </aside>
    <button v-if="mobileNavOpen" class="nav-scrim" aria-label="关闭导航" @click="mobileNavOpen = false" />

    <main class="main-area">
      <div v-if="serverOk && !publishingEnabled" class="publishing-disabled" role="status">
        <AlertTriangle :size="17" /><span><strong>真实发布已禁用</strong> 当前运行模式不包含可见浏览器，可继续编辑与预览；请在本机桌面模式启用发布。</span>
      </div>
      <header class="topbar">
        <div class="topbar-left">
          <button ref="mobileMenuButton" class="icon-button mobile-menu" aria-label="打开导航" aria-controls="workspace-sidebar" :aria-expanded="mobileNavOpen" @click="mobileNavOpen = true"><Menu :size="20" /></button>
          <span class="breadcrumb">工作空间</span><ChevronRight :size="14" /><strong>{{ pageTitle }}</strong>
        </div>
        <div class="topbar-right">
          <span class="date-label">{{ today }}</span>
          <span class="privacy-badge"><LockKeyhole :size="13" /> 数据仅存本机</span>
        </div>
      </header>

      <section v-if="view === 'editor'" class="view editor-view">
        <div class="page-heading editor-heading">
          <div>
            <div class="eyebrow"><span>COMPOSE</span><i></i><span>01</span></div>
            <h1>让内容，准确抵达。</h1>
            <p>写作、排版、发布，在一条安静的流里完成。</p>
          </div>
          <div class="heading-actions">
            <select v-if="articleDrafts.length" class="draft-select" aria-label="切换草稿" :value="draft.id" @change="loadDraft(articleDrafts.find((item) => item.id === Number(($event.target as HTMLSelectElement).value))!)">
              <option v-for="item in articleDrafts" :key="item.id" :value="item.id">{{ item.title }}</option>
            </select>
            <button class="button secondary" :disabled="saving" @click="saveDraft"><LoaderCircle v-if="saving" class="spin" :size="16" /><Save v-else :size="16" />保存草稿</button>
            <button class="button secondary" :disabled="saving" @click="prepareReuse"><Repeat2 :size="16" />一稿多发</button>
          </div>
        </div>

        <div class="workflow-strip" aria-label="发布流程">
          <div class="workflow-step active"><span>1</span><div><strong>写作</strong><small>生成或编辑内容</small></div></div>
          <i></i>
          <div class="workflow-step active"><span>2</span><div><strong>排版</strong><small>选择预设与封面</small></div></div>
          <i></i>
          <div class="workflow-step"><span>3</span><div><strong>发布</strong><small>确认后发往所选平台</small></div></div>
          <div class="workflow-note"><ShieldCheck :size="15" /> 发布前自动合规检查</div>
        </div>

        <div class="compose-grid">
          <section class="manuscript-panel">
            <div class="panel-title"><span class="section-index">A</span><h2>内容原稿</h2><button class="text-button" @click="useExample">填入示例 <ArrowUpRight :size="13" /></button></div>

            <div class="generator-box">
              <div class="generator-head"><span><Sparkles :size="15" /> AI 起稿</span><small>OpenAI 兼容模型</small></div>
              <textarea v-model="topic" rows="2" aria-label="文章主题" placeholder="这篇文章想聊什么？输入一个主题或关键词…"></textarea>
              <div class="generator-options">
                <select v-model="promptStyle" aria-label="写作风格">
                  <option>清晰、自然、有信息量</option><option>专业、严谨、适合知识分享</option><option>轻松、有故事感</option><option>简洁、直接、有观点</option>
                </select>
                <select v-model.number="targetLength" aria-label="目标字数"><option :value="800">约 800 字</option><option :value="1200">约 1200 字</option><option :value="2000">约 2000 字</option></select>
              </div>
              <button class="button generator-button" :disabled="generating" @click="generateArticle"><LoaderCircle v-if="generating" class="spin" :size="16" /><WandSparkles v-else :size="16" />{{ generating ? '正在创作…' : '生成文章' }}</button>
            </div>

            <label class="title-field"><span>标题</span><input v-model="draft.title" maxlength="300" placeholder="为内容写一个清晰的标题" /></label>
            <div class="editor-toolbar" aria-label="Markdown 格式工具">
              <button title="加粗" @click="applyFormat('**')"><b>B</b></button>
              <button title="斜体" @click="applyFormat('*')"><i>I</i></button>
              <span></span>
              <button title="二级标题" @click="applyFormat('\n## ', '')">H2</button>
              <button title="引用" @click="applyFormat('\n> ', '')"><BookOpenText :size="15" /></button>
              <span></span>
              <button title="插入链接" @click="applyFormat('[', '](https://)')">↗</button>
              <small>支持 Markdown</small>
            </div>
            <textarea ref="bodyEditor" v-model="draft.body" class="body-editor" aria-label="文章正文" placeholder="从这里开始写作…&#10;&#10;也可以在上方用 AI 生成初稿。"></textarea>
            <label class="tags-field" for="article-tags"><span>#</span><input id="article-tags" v-model="tagInput" placeholder="添加标签，用逗号分隔" @input="updateTags" /></label>
            <div class="manuscript-meta"><span>{{ stats.characters }} 字 · 预计阅读 {{ stats.readingMinutes }} 分钟</span><span>{{ draft.source === 'ai' ? 'AI 辅助' : '手动创作' }}</span></div>
          </section>

          <section class="preview-panel">
            <div class="preview-head">
              <div><span class="live-dot"></span><h2>实时预览</h2><span class="preview-preset">{{ activePreset?.name }}</span></div>
              <LoaderCircle v-if="previewLoading" class="spin" :size="16" />
            </div>
            <div class="preview-canvas">
              <div v-if="previewHtml" class="article-preview" v-html="previewHtml"></div>
              <div v-else class="preview-empty">
                <div class="empty-monogram">阅</div>
                <h3>内容会在这里展开</h3>
                <p>写下一个标题，或填入示例内容，<br />看看不同排版预设的样子。</p>
                <button class="text-button" @click="useExample">先看看示例 <ArrowUpRight :size="14" /></button>
              </div>
            </div>
            <div class="preview-foot"><span>预览已清理脚本与不安全样式</span><span>{{ activePreset?.platform_hint === 'wechat' ? '公众号风格' : '知乎风格' }} · {{ stats.characters }} 字</span></div>
          </section>

          <aside class="publish-panel">
            <div class="panel-title"><span class="section-index">B</span><h2>发布设置</h2></div>
            <div class="platform-card">
              <div class="platform-logo">{{ activeAccount ? platformInitial(activeAccount.platform) : 'C' }}</div>
              <div><strong>{{ activeAccount ? platformLabel(activeAccount.platform) : '选择发布平台' }}</strong><small>{{ activeAccount?.platform === 'zhihu' ? '知识社区 · 图文' : '技术博客 · 图文' }}</small></div>
              <span class="platform-tag">多平台</span>
            </div>

            <label class="setting-label" for="account-select">发布账号</label>
            <div class="select-wrap"><KeyRound :size="15" /><select id="account-select" v-model="selectedAccount"><option :value="null">请选择账号</option><option v-for="account in accounts.filter((item) => item.platform !== 'bilibili')" :key="account.id" :value="account.id">{{ platformLabel(account.platform) }} · {{ account.nickname }}</option></select></div>
            <button v-if="!accounts.length" class="inline-link" @click="changeView('accounts')">还没有账号，去导入 Cookie <ArrowUpRight :size="13" /></button>

            <label class="setting-label">排版预设</label>
            <div class="preset-pills"><button v-for="preset in presets" :key="preset.id" :class="{ active: selectedPreset === preset.id }" @click="selectedPreset = preset.id"><span :style="{ background: preset.style.accent }"></span>{{ preset.name }}<Check v-if="selectedPreset === preset.id" :size="13" /></button></div>

            <div class="delivery-settings">
              <label class="setting-label" for="scheduled-at">发布时间 <span class="optional-label">留空则立即发布</span></label>
              <input id="scheduled-at" v-model="scheduledAt" class="datetime-input" type="datetime-local" />
              <label class="setting-label" for="max-retries">安全自动重试</label>
              <div class="select-wrap"><RotateCcw :size="14" /><select id="max-retries" v-model.number="maxRetries"><option :value="0">不自动重试</option><option :value="1">失败后重试 1 次</option><option :value="2">失败后重试 2 次</option><option :value="3">失败后重试 3 次</option></select></div>
              <p class="setting-hint">仅明确可重试的失败会重试；结果不确定时绝不自动重复发布。</p>
            </div>

            <div class="setting-label cover-label"><span>文章封面</span><button class="text-button" @click="generateCover"><RefreshCw :class="{ spin: coverLoading }" :size="13" />重新生成</button></div>
            <div class="cover-box">
              <img v-if="draft.cover_image" :src="draft.cover_image" alt="文章封面预览" />
              <div v-else class="cover-placeholder"><ImageIcon :size="24" /><span>1200 × 630</span></div>
            </div>
            <div class="cover-source-actions">
              <button class="upload-background" @click="backgroundInput?.click()"><Upload :size="13" />使用自己的图片作背景</button>
              <button class="upload-background" @click="changeView('media')"><FolderOpen :size="13" />从素材库选择封面</button>
            </div>
            <input ref="backgroundInput" class="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" @change="uploadBackground" />

            <div class="compliance-box" :class="{ warning: findings.length }">
              <div class="compliance-title"><ShieldCheck :size="16" /><strong>发布前检查</strong><span class="platform-tag">服务端强制执行</span></div>
              <p v-if="blocked"><AlertTriangle :size="14" /> 包含禁止发布内容，已拦截。</p>
              <p v-else-if="findings.length"><AlertTriangle :size="14" /> 发现 {{ findings.length }} 项用语风险。</p>
              <p v-else><CircleCheck :size="14" /> 未发现内置规则风险。</p>
              <ul v-if="findings.length"><li v-for="finding in findings" :key="finding.message">{{ finding.message }}</li></ul>
              <label v-if="adFindings.length" class="ad-ack"><input v-model="articleAdAcknowledged" type="checkbox" />我已阅读风险，确认内容可以发布</label>
            </div>

            <label class="authorization"><input v-model="articleAuthorized" type="checkbox" /><span>我拥有内容版权或已获授权，并确认遵守 {{ activeAccount ? platformLabel(activeAccount.platform) : '目标平台' }} 自动化发布条款。</span></label>
            <button class="button publish-button" :disabled="blocked || publishing || !publishingEnabled" @click="preparePublish"><Send :size="17" />{{ scheduledAt ? '创建定时发布任务' : `发布到 ${activeAccount ? platformLabel(activeAccount.platform) : '所选平台'}` }}<ArrowUpRight :size="16" /></button>
            <p class="publish-note"><LockKeyhole :size="12" /> {{ scheduledAt ? '时间到达后打开本机浏览器，遇验证会停止' : '将打开本机浏览器，遇到验证会暂停' }}</p>
          </aside>
        </div>
      </section>

      <section v-else-if="view === 'video'" class="view video-view">
        <div class="page-heading video-heading">
          <div>
            <div class="eyebrow"><span>MOTION DESK</span><i></i><span>02</span></div>
            <h1>让画面，也准确抵达。</h1>
            <p>上传、抽帧、转码、投稿，视频流程和文章一样清晰。</p>
          </div>
          <div class="heading-actions">
            <select v-if="videoDrafts.length" class="draft-select" aria-label="切换视频草稿" :value="videoDraft.id" @change="loadVideoDraft(videoDrafts.find((item) => item.id === Number(($event.target as HTMLSelectElement).value))!)">
              <option v-for="item in videoDrafts" :key="item.id" :value="item.id">{{ item.title }}</option>
            </select>
            <button class="button secondary" @click="newVideoDraft"><Plus :size="16" />新建视频</button>
            <button class="button secondary" :disabled="saving" @click="saveVideoDraft"><LoaderCircle v-if="saving" class="spin" :size="16" /><Save v-else :size="16" />保存草稿</button>
          </div>
        </div>

        <div class="workflow-strip video-workflow" aria-label="视频发布流程">
          <div class="workflow-step" :class="{ active: !videoDraft.video_path }"><span>1</span><div><strong>上传</strong><small>校验时长与画面</small></div></div><i></i>
          <div class="workflow-step" :class="{ active: videoDraft.video_path }"><span>2</span><div><strong>整理</strong><small>封面、分区与简介</small></div></div><i></i>
          <div class="workflow-step"><span>3</span><div><strong>投稿</strong><small>浏览器上传至 B 站</small></div></div>
          <div class="workflow-note"><Film :size="15" /> 大文件由平台浏览器上传器传输</div>
        </div>

        <div class="video-grid">
          <section class="video-editor-panel">
            <div class="panel-title"><span class="section-index">A</span><h2>视频素材</h2><span class="video-platform-pill">MP4 · H.264 · AAC</span></div>
            <div v-if="!videoDraft.video_path" class="video-upload-zone" :class="{ loading: videoUploading }" @dragover.prevent @drop.prevent="dropVideoFile">
              <div class="upload-filmstrip"><span></span><span></span><span></span><span></span><span></span></div>
              <div class="upload-emblem"><VideoIcon :size="30" /></div>
              <h3>{{ videoUploading ? '正在上传并校验视频…' : '把视频拖到这里' }}</h3>
              <p>支持 MP4、MOV、WebM、MKV、M4V<br />最大 {{ videoConfig?.max_upload_mb || 4096 }} MB · 最长 {{ Math.round((videoConfig?.max_duration_seconds || 14400) / 60) }} 分钟</p>
              <button class="button primary" :disabled="videoUploading" @click="videoInput?.click()"><Upload :size="16" />选择本地视频</button>
              <button class="button secondary" :disabled="videoUploading" @click="changeView('media')"><FolderOpen :size="16" />从素材库选择</button>
              <input ref="videoInput" class="visually-hidden" type="file" accept=".mp4,.mov,.webm,.mkv,.m4v,video/*" @change="uploadVideoFile" />
            </div>
            <div v-else class="video-preview-block">
              <video :src="videoPreviewUrl" controls preload="metadata" aria-label="视频预览"></video>
              <div class="video-filebar">
                <div><strong>{{ videoFileLabel }}</strong><small>{{ videoDurationLabel }} · {{ videoDraft.video_width }} × {{ videoDraft.video_height }}{{ videoSize ? ` · ${formatBytes(videoSize)}` : '' }}</small></div>
                <button class="button secondary small" :disabled="videoUploading" @click="videoInput?.click()"><RefreshCw :size="14" />更换视频</button>
                <input ref="videoInput" class="visually-hidden" type="file" accept=".mp4,.mov,.webm,.mkv,.m4v,video/*" @change="uploadVideoFile" />
              </div>
            </div>

            <div class="video-copy-fields">
              <label class="title-field"><span>投稿标题 <small>{{ videoDraft.title.length }}/80</small></span><input v-model="videoDraft.title" maxlength="80" placeholder="一个清晰、有辨识度的标题" /></label>
              <label class="form-label">视频简介 <small>选填，最多 2000 字</small><textarea v-model="videoDraft.body" rows="6" maxlength="2000" placeholder="介绍视频内容、创作背景或观看重点…"></textarea></label>
              <label class="tags-field" for="video-tags"><span>#</span><input id="video-tags" v-model="videoTagInput" placeholder="添加话题标签，用逗号分隔" @input="updateVideoTags" /></label>
            </div>

            <div class="video-tools">
              <div class="video-tool-heading"><span class="section-index">B</span><h2>封面与编码</h2></div>
              <div class="video-tool-grid">
                <div class="video-cover-tool">
                  <div class="video-cover-preview">
                    <img v-if="videoDraft.cover_image" :src="videoDraft.cover_image" alt="视频封面预览" />
                    <div v-else><ImageIcon :size="24" /><span>从画面开始</span></div>
                  </div>
                  <label class="form-label">抽帧时间（秒）<input v-model="coverAtSeconds" type="number" min="0" step="0.1" placeholder="默认第 1 秒" /></label>
                  <button class="button secondary full-width" :disabled="!videoDraft.video_path || videoProcessing === 'cover'" @click="extractVideoCover"><LoaderCircle v-if="videoProcessing === 'cover'" class="spin" :size="15" /><Scissors v-else :size="15" />抽帧并生成封面</button>
                </div>
                <div class="transcode-tool">
                  <div class="transcode-icon"><Film :size="24" /></div>
                  <h3>兼容性转码</h3>
                  <p>输出 H.264 / AAC MP4，限制画面宽度并启用 faststart，适合浏览器大文件上传。</p>
                  <button class="button secondary full-width" :disabled="!videoDraft.video_path || videoProcessing === 'transcode'" @click="transcodeVideoFile"><LoaderCircle v-if="videoProcessing === 'transcode'" class="spin" :size="15" /><RefreshCw v-else :size="15" />{{ videoProcessing === 'transcode' ? '正在转码…' : '转为发布兼容格式' }}</button>
                </div>
              </div>
            </div>
          </section>

          <aside class="publish-panel video-publish-panel">
            <div class="panel-title"><span class="section-index">C</span><h2>投稿设置</h2><span class="platform-tag">视频</span></div>
            <div class="platform-card bilibili-card">
              <div class="platform-logo">B</div><div><strong>哔哩哔哩</strong><small>视频投稿 · 分区与合集</small></div><VideoIcon :size="18" />
            </div>
            <label class="setting-label" for="video-account-select">投稿账号</label>
            <div class="select-wrap"><KeyRound :size="15" /><select id="video-account-select" v-model="selectedVideoAccount"><option :value="null">请选择 B 站账号</option><option v-for="account in accounts.filter((item) => item.platform === 'bilibili')" :key="account.id" :value="account.id">{{ account.nickname }}</option></select></div>
            <button v-if="!accounts.some((item) => item.platform === 'bilibili')" class="inline-link" @click="changeView('accounts')">还没有 B 站账号，去导入 Cookie <ArrowUpRight :size="13" /></button>

            <div class="form-row video-classification">
              <label class="form-label">内容分区<select v-model="videoDraft.video_partition"><option v-for="partition in BILIBILI_PARTITIONS" :key="partition" :value="partition">{{ partition }}</option></select></label>
              <label class="form-label">加入合集 <small>选填</small><input v-model="videoDraft.video_collection" maxlength="120" placeholder="已有合集名称" /></label>
            </div>
            <p class="setting-hint collection-hint"><FolderOpen :size="13" /> 合集必须已存在于你的 B 站账号中；名称不一致时会在投稿前停止。</p>

            <div class="delivery-settings">
              <label class="setting-label" for="video-scheduled-at">发布时间 <span class="optional-label">留空则立即投稿</span></label>
              <input id="video-scheduled-at" v-model="videoScheduledAt" class="datetime-input" type="datetime-local" />
              <label class="setting-label" for="video-max-retries">安全自动重试</label>
              <div class="select-wrap"><RotateCcw :size="14" /><select id="video-max-retries" v-model.number="maxRetries"><option :value="0">不自动重试</option><option :value="1">失败后重试 1 次</option><option :value="2">失败后重试 2 次</option><option :value="3">失败后重试 3 次</option></select></div>
              <p class="setting-hint">仅上传准备阶段的明确失败会重试。点击投稿后若无回执，必须人工确认。</p>
            </div>

            <div class="compliance-box" :class="{ warning: videoFindings.length }">
              <div class="compliance-title"><ShieldCheck :size="16" /><strong>标题与简介检查</strong><span class="platform-tag">服务端强制执行</span></div>
              <p v-if="videoBlocked"><AlertTriangle :size="14" /> 包含禁止发布内容，已拦截。</p>
              <p v-else-if="videoFindings.length"><AlertTriangle :size="14" /> 发现 {{ videoFindings.length }} 项用语风险。</p>
              <p v-else><CircleCheck :size="14" /> 未发现内置规则风险。</p>
              <ul v-if="videoFindings.length"><li v-for="finding in videoFindings" :key="finding.message">{{ finding.message }}</li></ul>
              <label v-if="videoAdFindings.length" class="ad-ack"><input v-model="videoAdAcknowledged" type="checkbox" />我已阅读风险，确认内容可以投稿</label>
            </div>

            <label class="authorization"><input v-model="videoAuthorized" type="checkbox" /><span>我拥有视频与封面版权或已获授权，并确认遵守哔哩哔哩自动化发布条款。</span></label>
            <button class="button publish-button" :disabled="!videoReady || videoBlocked || publishing || !publishingEnabled" @click="prepareVideoPublish"><Send :size="17" />{{ videoScheduledAt ? '创建定时投稿任务' : '投稿到哔哩哔哩' }}<ArrowUpRight :size="16" /></button>
            <p class="publish-note"><LockKeyhole :size="12" /> {{ videoScheduledAt ? '时间到达后打开本机浏览器上传' : '将打开本机浏览器上传，遇到验证会停止' }}</p>
          </aside>
        </div>
      </section>

      <section v-else-if="view === 'media'" class="view media-view">
        <MediaLibrary @use="useMediaImage" @use-video="useMediaVideo" />
      </section>

      <section v-else-if="view === 'records'" class="view records-view">
        <div class="page-heading"><div><div class="eyebrow"><span>PUBLISH LOG</span><i></i><span>04</span></div><h1>每一次发布，都有迹可循。</h1><p>状态、平台回执与审计记录，都留在本机。</p></div><button class="button secondary" @click="loadTasks"><RefreshCw :size="16" />刷新记录</button></div>
        <div class="record-stats">
          <div><span>累计任务</span><strong>{{ String(tasks.length).padStart(2, '0') }}</strong><small>所有发布记录</small></div>
          <div><span>发布成功</span><strong>{{ String(successfulTasks).padStart(2, '0') }}</strong><small>平台已确认回执</small></div>
          <div><span>正在处理</span><strong>{{ String(runningTasks.length).padStart(2, '0') }}</strong><small>请勿重复提交</small></div>
          <div class="stat-decoration"><History :size="42" /><span>本地审计日志<br />不可隐藏的发布轨迹</span></div>
        </div>
        <div class="records-list">
          <div v-if="!tasks.length" class="large-empty"><History :size="32" /><h2>还没有发布记录</h2><p>完成第一次发布后，平台回执与操作日志会出现在这里。</p><button class="button primary" @click="changeView('editor')">开始创作 <ArrowUpRight :size="16" /></button></div>
          <article v-for="task in tasks" :key="task.id" class="task-item">
            <div class="task-main">
              <div class="task-status-icon" :class="task.status"><LoaderCircle v-if="task.status === 'running'" class="spin" :size="20" /><CheckCircle2 v-else-if="task.status === 'success'" :size="20" /><Pause v-else-if="task.status === 'paused'" :size="20" /><Clock3 v-else-if="task.status === 'pending'" :size="20" /><AlertTriangle v-else :size="20" /></div>
              <div class="task-copy">
                <div class="task-title-line"><h3>{{ task.draft_title }}</h3><span class="status-chip" :class="task.status">{{ statusLabel(task.status) }}</span></div>
                <p><VideoIcon v-if="task.content_type === 'video'" :size="12" />{{ platformLabel(task.platform) }} · {{ task.content_type === 'video' ? '视频' : '文章' }} · 任务 #{{ task.id }} · {{ formatTime(task.created_at) }}{{ task.retry_count ? ` · 已重试 ${task.retry_count}/${task.max_retries} 次` : '' }}</p>
                <p v-if="task.scheduled_at"><CalendarClock :size="12" /> 计划执行：{{ formatTime(task.scheduled_at) }}</p>
                <p v-else-if="task.next_retry_at"><RotateCcw :size="12" /> 下次重试：{{ formatTime(task.next_retry_at) }}</p>
                <p v-if="task.submission_uncertain" class="task-error"><AlertTriangle :size="13" /> 平台提交结果不确定，请先在平台确认，勿直接重复发布。</p>
                <div v-if="task.error_msg" class="task-error">{{ task.error_msg }}</div>
              </div>
              <div class="task-actions">
                <a v-if="task.result_url" :href="task.result_url" target="_blank" rel="noopener noreferrer" class="button secondary small">{{ task.content_type === 'video' ? '查看稿件' : '查看文章' }} <ExternalLink :size="14" /></a>
                <button v-if="task.status === 'pending'" class="button ghost small" :disabled="taskBusyId === task.id" @click="controlTask(task, 'pause')"><Pause :size="14" />暂停</button>
                <button v-if="task.status === 'paused'" class="button ghost small" :disabled="taskBusyId === task.id" @click="controlTask(task, 'resume')"><Play :size="14" />恢复</button>
                <button v-if="!['running', 'success'].includes(task.status)" class="button ghost small" :disabled="taskBusyId === task.id" @click="controlTask(task, 'skip')"><SkipForward :size="14" />跳过</button>
                <button v-if="task.status === 'failed'" class="button ghost small" :disabled="manualRetryBlocked(task)" :title="manualRetryBlocked(task) ? '结果不确定，请先在平台确认文章状态' : '重新提交任务'" @click="retryTask(task)"><RotateCcw :size="14" />重试</button>
                <button class="icon-button" :aria-label="expandedTask === task.id ? '收起日志' : '查看日志'" @click="expandedTask = expandedTask === task.id ? null : task.id"><ChevronRight :size="18" :class="{ rotated: expandedTask === task.id }" /></button>
              </div>
            </div>
            <div v-if="expandedTask === task.id" class="task-logs"><div class="log-heading">审计日志 <span>{{ task.logs.length }} 条</span></div><div v-for="(log, index) in task.logs" :key="index" class="log-line"><span class="log-level" :class="log.level">{{ log.level }}</span><time>{{ formatTime(log.created_at) }}</time><p>{{ log.message }}</p></div></div>
          </article>
        </div>
        <AuditTrail />
      </section>

      <section v-else-if="view === 'analytics'" class="view analytics-view">
        <div class="page-heading"><div><div class="eyebrow"><span>LOCAL INTELLIGENCE</span><i></i><span>05</span></div><h1>看见每一次发布的回响。</h1><p>汇总本机任务与合规回采数据，不连接平台私密页面。</p></div><span class="security-seal"><ShieldCheck :size="20" /><span>数据边界<br /><strong>官方来源 · 本地留存</strong></span></span></div>
        <AnalyticsDashboard @saved="notify('平台指标已保存，看板已更新')" />
      </section>

      <section v-else-if="view === 'accounts'" class="view accounts-view">
        <div class="page-heading"><div><div class="eyebrow"><span>LOCAL VAULT</span><i></i><span>06</span></div><h1>账号留在本地，权限握在你手里。</h1><p>只导入自己的账号，凭证加密保存，不经过云端。</p></div><span class="security-seal"><LockKeyhole :size="20" /><span>Fernet<br /><strong>本地加密</strong></span></span></div>
        <div class="accounts-grid">
          <section class="import-panel">
            <div class="panel-title"><span class="section-index">+</span><h2>导入平台登录态</h2></div>
            <ol class="import-steps"><li><span>1</span><p>在浏览器登录自己的 {{ platformLabel(accountPlatform) }} 账号。</p></li><li><span>2</span><p>用 CookieJSON 类扩展导出当前站点 Cookie。</p></li><li><span>3</span><p>粘贴下方 JSON，PublishFlow 会加密保存。</p></li></ol>
            <div class="form-label">发布平台<div class="platform-options"><button type="button" :class="{ active: accountPlatform === 'csdn' }" @click="accountPlatform = 'csdn'; changeImportPlatform()">CSDN</button><button type="button" :class="{ active: accountPlatform === 'zhihu' }" @click="accountPlatform = 'zhihu'; changeImportPlatform()">知乎</button><button type="button" :class="{ active: accountPlatform === 'bilibili' }" @click="accountPlatform = 'bilibili'; changeImportPlatform()">哔哩哔哩</button></div></div>
            <label class="form-label">账号备注<input v-model="nickname" maxlength="120" placeholder="例如：我的技术博客" /></label>
            <label class="form-label">Cookie JSON<textarea v-model="cookieJson" rows="8" spellcheck="false" :placeholder='`[{"name":"...","value":"...","domain":".${({ csdn: "csdn.net", zhihu: "zhihu.com", bilibili: "bilibili.com" })[accountPlatform]}",...}]`'></textarea></label>
            <button class="button primary full-width" :disabled="importing || !cookieJson.trim()" @click="importAccount"><LoaderCircle v-if="importing" class="spin" :size="16" /><Plus v-else :size="16" />加密保存账号</button>
            <p class="form-note"><ShieldCheck :size="13" /> 请勿分享 Cookie。导出文件也应妥善删除。</p>
          </section>
          <section class="account-list-panel">
            <div class="panel-title"><span class="section-index">C</span><h2>已保存账号</h2><span class="count-badge">{{ accounts.length }}</span></div>
            <div v-if="!accounts.length" class="account-empty"><KeyRound :size="30" /><h3>本地保险库还是空的</h3><p>导入 Cookie 后即可验证登录态并发布。</p></div>
            <article v-for="account in accounts" :key="account.id" class="account-item">
              <div class="account-avatar" :class="account.platform">{{ platformInitial(account.platform) }}</div><div class="account-info"><h3>{{ account.nickname }}</h3><p>{{ platformLabel(account.platform) }} · {{ account.login_valid ? '登录态可用' : '登录态待验证' }}</p><span :class="{ valid: account.login_valid }"><i></i>{{ account.login_valid ? '已加密存储' : '请重新验证' }}</span></div>
              <div class="account-actions"><button class="button secondary small" :disabled="validatingId === account.id" @click="validateAccount(account)"><LoaderCircle v-if="validatingId === account.id" class="spin" :size="14" /><RefreshCw v-else :size="14" />验证</button><button class="icon-button danger" :aria-label="`删除 ${account.nickname}`" @click="removeAccount(account)"><Trash2 :size="16" /></button></div>
            </article>
            <div class="security-note"><ShieldCheck :size="22" /><div><strong>关于本地凭证</strong><p>密钥默认保存在数据目录并限制文件权限。备份项目时请排除 <code>data/</code> 与 <code>.env</code>。发布动作只针对你明确选择的账号。</p></div></div>
          </section>
        </div>
      </section>

      <section v-else-if="view === 'schedules'" class="view schedules-view">
        <div class="page-heading">
          <div><div class="eyebrow"><span>DELIVERY QUEUE</span><i></i><span>08</span></div><h1>把发布，安排得从容一些。</h1><p>一次性定时或周期执行，多账号自动错峰，所有状态清晰可见。</p></div>
          <button class="button primary" :disabled="!publishingEnabled" @click="openScheduleForm"><Plus :size="16" />新建调度计划</button>
        </div>
        <div class="schedule-overview">
          <div><CalendarClock :size="20" /><span>启用中的计划<strong>{{ activeSchedules }}</strong></span></div>
          <div><Clock3 :size="20" /><span>等待与执行中<strong>{{ runningTasks.length }}</strong></span></div>
          <div><ShieldCheck :size="20" /><span>执行策略<strong>授权复核 · 自动错峰</strong></span></div>
        </div>
        <div class="schedule-grid" :class="{ 'form-hidden': !showScheduleForm }">
          <section v-if="showScheduleForm" class="schedule-form-panel">
            <div class="panel-title"><span class="section-index">+</span><h2>新建调度计划</h2><button class="icon-button" aria-label="关闭计划表单" @click="showScheduleForm = false"><X :size="17" /></button></div>
            <label class="form-label">计划名称<input v-model="scheduleName" maxlength="120" placeholder="例如：每周技术分享" /></label>
            <div class="form-row">
              <label class="form-label">发布草稿<select v-model="scheduleDraftId"><option :value="null">请选择草稿</option><option v-for="item in drafts" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
              <label class="form-label">{{ scheduleDraft?.content_type === 'video' ? '任务预设（视频不使用）' : '排版预设' }}<select v-model="selectedPreset"><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.name }}</option></select></label>
            </div>
            <div class="form-label">执行方式<div class="platform-options schedule-mode"><button type="button" :class="{ active: scheduleMode === 'once' }" @click="scheduleMode = 'once'"><CalendarClock :size="14" />一次性定时</button><button type="button" :class="{ active: scheduleMode === 'cron' }" @click="scheduleMode = 'cron'"><Repeat2 :size="14" />周期计划</button></div></div>
            <label v-if="scheduleMode === 'once'" class="form-label">执行时间<input v-model="scheduleAt" type="datetime-local" /></label>
            <label v-else class="form-label">Cron 表达式<input v-model="cronExpr" placeholder="30 9 * * *" spellcheck="false" /><small>5 段格式：分钟 小时 日 月 星期，按本机调度时区执行。</small></label>
            <div class="form-label">发布账号 <small>可多选，系统会按选择顺序错峰创建任务</small><div class="account-checkboxes"><label v-for="account in scheduleAccounts" :key="account.id"><input type="checkbox" :checked="scheduleAccountIds.includes(account.id)" @change="toggleScheduleAccount(account.id)" /><span>{{ platformLabel(account.platform) }} · {{ account.nickname }}</span></label><p v-if="!scheduleAccounts.length" class="form-note">没有与所选内容类型匹配的账号。</p></div></div>
            <label class="schedule-authorization"><input v-model="scheduleAuthorized" type="checkbox" /><span>我确认计划中的内容归本人所有或已获授权，并允许系统在指定时间操作所选账号。</span></label>
            <button class="button primary full-width" :disabled="scheduleSaving || !drafts.length || !accounts.length" @click="createSchedule"><LoaderCircle v-if="scheduleSaving" class="spin" :size="16" /><CalendarClock v-else :size="16" />创建调度计划</button>
            <p class="form-note"><ShieldCheck :size="13" /> 每次执行前会再次检查授权与内容合规状态。</p>
          </section>
          <section class="schedule-list-panel">
            <div class="panel-title"><span class="section-index">C</span><h2>调度计划</h2><span class="count-badge">{{ schedules.length }}</span></div>
            <div v-if="!showScheduleForm && !schedules.length" class="large-empty schedule-empty"><CalendarClock :size="32" /><h2>还没有调度计划</h2><p>为即将发布的内容安排一个时间，或创建每周自动执行的计划。</p><button class="button primary" @click="openScheduleForm">创建第一个计划 <ArrowUpRight :size="16" /></button></div>
            <article v-for="plan in schedules" :key="plan.id" class="schedule-item" :class="{ disabled: !plan.enabled }">
              <div class="schedule-item-head"><div class="schedule-emblem"><Repeat2 v-if="plan.cron_expr" :size="19" /><CalendarClock v-else :size="19" /></div><div><h3>{{ plan.name }}</h3><p>{{ plan.content_type === 'video' ? '视频 · ' : '' }}{{ plan.draft_title }}</p></div><span class="status-chip" :class="{ success: plan.enabled }">{{ plan.enabled ? '已启用' : '已暂停' }}</span></div>
              <div class="schedule-item-meta"><span><Clock3 :size="13" />{{ plan.cron_expr || (plan.scheduled_at ? formatTime(plan.scheduled_at) : '时间待定') }}</span><span><KeyRound :size="13" />{{ plan.account_names.join('、') || '账号已删除' }}</span></div>
              <p v-if="!plan.authorization_valid" class="schedule-warning"><AlertTriangle :size="13" /> 草稿、模板或媒体已变化，原授权失效；请重新创建计划。</p>
              <div class="schedule-next"><span>下次执行</span><strong>{{ plan.enabled && plan.next_run_at ? formatTime(plan.next_run_at) : '—' }}</strong></div>
              <div class="schedule-item-actions"><button class="button secondary small" :disabled="!plan.authorization_valid && !plan.enabled" @click="toggleSchedule(plan)"><Pause v-if="plan.enabled" :size="14" /><Play v-else :size="14" />{{ plan.enabled ? '暂停计划' : '启用计划' }}</button><button class="button ghost small" @click="removeSchedule(plan)"><Trash2 :size="14" />删除</button></div>
            </article>
          </section>
        </div>
      </section>

      <section v-else-if="view === 'presets'" class="view presets-view">
        <TemplateEditor ref="templateEditor" :presets="presets" @saved="reloadPresets" @apply="selectPreset" />
      </section>
    </main>

    <Transition name="modal">
      <div v-if="showReuseModal" class="modal-backdrop" role="presentation" @click.self="closeReuseModal">
      <section ref="reuseModal" class="publish-modal reuse-modal" role="dialog" aria-modal="true" aria-labelledby="reuse-modal-title" tabindex="-1" @keydown="handleReuseModalKeydown">
          <button class="icon-button modal-close" aria-label="关闭" :disabled="reusing" @click="closeReuseModal"><X :size="19" /></button>
          <div class="modal-emblem"><Repeat2 :size="23" /></div><div class="eyebrow"><span>ONE DRAFT · MORE PLATFORMS</span></div>
          <h2 id="reuse-modal-title">让一份原稿，有多种表达。</h2>
          <p class="modal-intro">从「{{ draft.title }}」创建独立文章版本。原稿不会被修改，新版本也不会自动发布。</p>
          <div class="reuse-field"><span>目标平台</span><div class="platform-options"><button type="button" :class="{ active: reuseTarget === 'csdn' }" :disabled="reusing" @click="reuseTarget = 'csdn'">CSDN 技术博客</button><button type="button" :class="{ active: reuseTarget === 'zhihu' }" :disabled="reusing" @click="reuseTarget = 'zhihu'">知乎知识社区</button></div></div>
          <label class="reuse-adapt"><input v-model="reuseAdapt" type="checkbox" :disabled="reusing" /><span><strong>使用模型进行平台适配改写</strong><small>保留事实、观点与素材引用，不虚构经历、数据或来源。需先配置模型 API；未勾选时仅复制原稿。</small></span></label>
          <div class="modal-warning"><ShieldCheck :size="17" /><p>适配结果仍需人工核对。新版本会沿用封面与标签，之后可在编辑台继续修改并单独发布。</p></div>
          <div class="modal-actions"><button class="button secondary" :disabled="reusing" @click="closeReuseModal">取消</button><button class="button primary" :disabled="reusing" @click="confirmReuse"><LoaderCircle v-if="reusing" class="spin" :size="16" /><Repeat2 v-else :size="16" />{{ reusing ? '正在创建版本…' : '创建独立版本' }}</button></div>
        </section>
      </div>
    </Transition>

    <Transition name="modal">
      <div v-if="showPublishModal" class="modal-backdrop" role="presentation" @click.self="!publishing && (showPublishModal = false)">
        <section ref="publishModal" class="publish-modal" role="dialog" aria-modal="true" aria-labelledby="publish-modal-title" tabindex="-1" @keydown="handlePublishModalKeydown">
          <button class="icon-button modal-close" aria-label="关闭" :disabled="publishing" @click="showPublishModal = false"><X :size="19" /></button>
          <div class="modal-emblem"><Send :size="23" /></div><div class="eyebrow"><span>FINAL CHECK</span></div><h2 id="publish-modal-title">{{ modalScheduledAt ? '确认创建定时任务？' : `确认${view === 'video' ? '投稿' : '发布'}到 ${modalAccount ? platformLabel(modalAccount.platform) : '所选平台'}？` }}</h2><p class="modal-intro">这会操作你的真实账号。请最后核对一次发布信息。</p>
          <div class="modal-summary"><div><span>账号</span><strong>{{ modalAccount?.nickname }}</strong></div><div v-if="view === 'editor'"><span>排版</span><strong>{{ activePreset?.name }}</strong></div><div v-if="view === 'video'"><span>分区</span><strong>{{ videoDraft.video_partition }}{{ videoDraft.video_collection ? ` · ${videoDraft.video_collection}` : '' }}</strong></div><div><span>标题</span><strong>{{ modalDraft.title }}</strong></div><div><span>时间</span><strong>{{ modalScheduledAt ? formatTime(new Date(modalScheduledAt).toISOString()) : '立即执行' }}</strong></div><div><span>重试</span><strong>{{ maxRetries ? `最多 ${maxRetries} 次安全重试` : '不自动重试' }}</strong></div></div>
          <div class="modal-warning"><AlertTriangle :size="17" /><p>{{ modalScheduledAt ? '时间到达后才会打开本机浏览器执行。' : '将打开本机浏览器执行。' }}{{ view === 'video' ? '大文件上传可能持续较长时间；点击投稿后若无回执，必须先在 B 站确认。' : '遇到验证码或页面改版时，PublishFlow 会停止并提示你人工处理。' }}</p></div>
          <div class="modal-actions"><button class="button secondary" :disabled="publishing" @click="showPublishModal = false">返回检查</button><button class="button primary" :disabled="publishing" @click="view === 'video' ? confirmVideoPublish() : confirmPublish()"><LoaderCircle v-if="publishing" class="spin" :size="16" /><Send v-else :size="16" />{{ publishing ? '正在提交…' : (modalScheduledAt ? '确认创建任务' : '确认发布') }}</button></div>
        </section>
      </div>
    </Transition>

    <Transition name="toast"><div v-if="toast" class="toast" role="status"><CheckCircle2 :size="17" /><span>{{ toast }}</span><button aria-label="关闭提示" @click="toast = ''"><X :size="15" /></button></div></Transition>
  </div>
</template>
