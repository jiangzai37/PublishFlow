<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertCircle, ArrowUpRight, Check, Film, HardDrive, Image as ImageIcon, LoaderCircle,
  RefreshCw, Search, Shuffle, Tag, Trash2, Upload, WandSparkles, X,
} from 'lucide-vue-next'
import { api } from '../api'
import type { AssetCapabilities, MediaAsset } from '../types'

type KindFilter = 'all' | MediaAsset['kind']
type NoticeTone = 'success' | 'error' | 'info'

const emit = defineEmits<{
  use: [asset: MediaAsset]
  'use-video': [asset: MediaAsset]
}>()

const DEFAULT_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
const VIDEO_ACCEPT = 'video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.m4v'
const SOURCE_LABELS: Record<string, string> = {
  upload: '本地上传',
  ai: 'AI 生成',
  cover: '封面提取',
  video: '视频提取',
  transcode: '视频转码',
  manual: '手动导入',
}

const assets = ref<MediaAsset[]>([])
const capabilities = ref<AssetCapabilities | null>(null)
const capabilitiesError = ref('')
const loading = ref(true)
const loadError = ref('')
const activeKind = ref<KindFilter>('all')
const queryDraft = ref('')
const tagDraft = ref('')
const appliedQuery = ref('')
const appliedTag = ref('')
const randomKind = ref<'image' | 'video'>('image')
const randomizing = ref(false)
const selectedId = ref<number | null>(null)
const editingId = ref<number | null>(null)
const editingTags = ref('')
const savingTags = ref(false)
const confirmingDeleteId = ref<number | null>(null)
const deleting = ref(false)
const uploadingImage = ref(false)
const uploadingVideo = ref(false)
const generating = ref(false)
const imageTags = ref('')
const generationPrompt = ref('')
const generationTags = ref('')
const imageInput = ref<HTMLInputElement | null>(null)
const videoInput = ref<HTMLInputElement | null>(null)
const failedPreviews = ref(new Set<number>())
const notice = ref('')
const noticeTone = ref<NoticeTone>('info')
let loadSequence = 0

const selectedAsset = computed(() => assets.value.find((asset) => asset.id === selectedId.value) ?? null)
const knownTags = computed(() => [...new Set(assets.value.flatMap((asset) => asset.tags))].sort((a, b) => a.localeCompare(b, 'zh-CN')))
const imageAccept = computed(() => {
  const extensions = capabilities.value?.image_extensions ?? DEFAULT_IMAGE_EXTENSIONS
  return `image/jpeg,image/png,image/webp,${extensions.map((extension) => extension.startsWith('.') ? extension : `.${extension}`).join(',')}`
})
const maxImageMb = computed(() => capabilities.value?.max_image_upload_mb ?? 10)
const resultSummary = computed(() => {
  const kind = activeKind.value === 'all' ? '全部素材' : activeKind.value === 'image' ? '图片' : '视频'
  return `${kind} · ${assets.value.length} 项`
})

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

function setNotice(message: string, tone: NoticeTone = 'info') {
  notice.value = message
  noticeTone.value = tone
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function formatDuration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return '时长待读取'
  const rounded = Math.max(0, Math.round(seconds))
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const remainder = rounded % 60
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}

function dimensions(asset: MediaAsset) {
  return asset.width && asset.height ? `${asset.width} × ${asset.height}` : '尺寸待读取'
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] ?? source
}

function parseTags(value: string) {
  return [...new Set(value.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean))]
}

async function loadAssets() {
  const sequence = ++loadSequence
  loading.value = true
  loadError.value = ''
  try {
    const result = await api.assets({
      kind: activeKind.value === 'all' ? undefined : activeKind.value,
      q: appliedQuery.value || undefined,
      tag: appliedTag.value || undefined,
    })
    if (sequence !== loadSequence) return
    assets.value = result
    if (selectedId.value !== null && !result.some((asset) => asset.id === selectedId.value)) {
      selectedId.value = null
      editingId.value = null
      confirmingDeleteId.value = null
    }
  } catch (error) {
    if (sequence === loadSequence) loadError.value = errorMessage(error, '素材列表加载失败，请确认本地服务正在运行。')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function loadCapabilities() {
  capabilitiesError.value = ''
  try {
    capabilities.value = await api.assetCapabilities()
  } catch (error) {
    capabilitiesError.value = errorMessage(error, '生图能力状态读取失败，请刷新后重试。')
  }
}

function setKind(kind: KindFilter) {
  if (activeKind.value === kind) return
  activeKind.value = kind
  if (kind !== 'all') randomKind.value = kind
  editingId.value = null
  confirmingDeleteId.value = null
  void loadAssets()
}

function applyFilters() {
  appliedQuery.value = queryDraft.value.trim()
  appliedTag.value = tagDraft.value.trim()
  void loadAssets()
}

function clearFilters() {
  queryDraft.value = ''
  tagDraft.value = ''
  appliedQuery.value = ''
  appliedTag.value = ''
  void loadAssets()
}

function filterByTag(tag: string) {
  tagDraft.value = tag
  appliedTag.value = tag
  void loadAssets()
}

function selectAsset(asset: MediaAsset) {
  selectedId.value = asset.id
  editingId.value = null
  confirmingDeleteId.value = null
}

function useAsset(asset: MediaAsset) {
  selectAsset(asset)
  if (asset.kind === 'image') emit('use', asset)
  else emit('use-video', asset)
}

async function revealAsset(asset: MediaAsset) {
  if (activeKind.value !== 'all' && activeKind.value !== asset.kind) activeKind.value = asset.kind
  if (asset.kind === 'video') randomKind.value = 'video'
  queryDraft.value = ''
  appliedQuery.value = ''
  tagDraft.value = ''
  appliedTag.value = ''
  selectedId.value = asset.id
  editingId.value = null
  await loadAssets()
}

async function pickRandom() {
  if (randomizing.value) return
  randomizing.value = true
  try {
    const asset = await api.randomAsset(randomKind.value, appliedTag.value || undefined)
    if (activeKind.value !== 'all' && activeKind.value !== asset.kind) activeKind.value = asset.kind
    queryDraft.value = ''
    appliedQuery.value = ''
    selectedId.value = asset.id
    editingId.value = null
    confirmingDeleteId.value = null
    assets.value = [asset, ...assets.value.filter((item) => item.id !== asset.id)]
    setNotice(`已随机选中「${asset.original_name}」，确认后即可使用。`, 'success')
  } catch (error) {
    setNotice(errorMessage(error, '随机选取失败，请先上传素材或调整标签。'), 'error')
  } finally {
    randomizing.value = false
  }
}

function validateImage(file: File) {
  const extension = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : ''
  const allowed = capabilities.value?.image_extensions ?? DEFAULT_IMAGE_EXTENSIONS
  if (!allowed.includes(extension)) {
    throw new Error(`图片仅支持 ${allowed.join('、')} 格式。`)
  }
  if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    throw new Error('上传文件的类型不是受支持的图片。')
  }
  if (file.size === 0) throw new Error('图片文件不能为空。')
  if (file.size > maxImageMb.value * 1024 * 1024) throw new Error(`图片不能超过 ${maxImageMb.value} MB。`)
}

async function uploadImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || uploadingImage.value) return
  uploadingImage.value = true
  try {
    validateImage(file)
    const asset = await api.uploadAsset(file, imageTags.value.trim())
    imageTags.value = ''
    await revealAsset(asset)
    setNotice(`「${asset.original_name}」已保存到本地素材库。`, 'success')
  } catch (error) {
    setNotice(errorMessage(error, '图片上传失败。'), 'error')
  } finally {
    uploadingImage.value = false
  }
}

async function uploadVideo(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || uploadingVideo.value) return
  uploadingVideo.value = true
  try {
    if (file.size === 0) throw new Error('视频文件不能为空。')
    await api.uploadVideo(file)
    await revealAssetByKind('video')
    setNotice('视频已上传并自动登记到素材库，可继续整理标签。', 'success')
  } catch (error) {
    setNotice(errorMessage(error, '视频上传失败，请检查格式与文件大小。'), 'error')
  } finally {
    uploadingVideo.value = false
  }
}

async function revealAssetByKind(kind: MediaAsset['kind']) {
  activeKind.value = kind
  randomKind.value = kind
  queryDraft.value = ''
  appliedQuery.value = ''
  tagDraft.value = ''
  appliedTag.value = ''
  await loadAssets()
}

async function generateImage() {
  const prompt = generationPrompt.value.trim()
  if (!prompt || generating.value || !capabilities.value?.image_generation_configured) return
  generating.value = true
  try {
    const asset = await api.generateAsset(prompt, parseTags(generationTags.value))
    generationPrompt.value = ''
    generationTags.value = ''
    await revealAsset(asset)
    setNotice('图片已生成并保存到本地素材库。', 'success')
  } catch (error) {
    setNotice(errorMessage(error, 'AI 生图失败，请检查本机服务配置后重试。'), 'error')
  } finally {
    generating.value = false
  }
}

function beginTagEdit(asset: MediaAsset) {
  selectedId.value = asset.id
  editingId.value = asset.id
  editingTags.value = asset.tags.join('，')
  confirmingDeleteId.value = null
}

function cancelTagEdit() {
  editingId.value = null
  editingTags.value = ''
}

async function saveTags(asset: MediaAsset) {
  if (savingTags.value) return
  savingTags.value = true
  try {
    const updated = await api.updateAsset(asset.id, parseTags(editingTags.value))
    assets.value = assets.value.map((item) => item.id === updated.id ? updated : item)
    selectedId.value = updated.id
    editingId.value = null
    editingTags.value = ''
    setNotice('素材标签已更新。', 'success')
    if (appliedQuery.value || appliedTag.value) await loadAssets()
  } catch (error) {
    setNotice(errorMessage(error, '标签保存失败。'), 'error')
  } finally {
    savingTags.value = false
  }
}

function askDelete(asset: MediaAsset) {
  selectedId.value = asset.id
  editingId.value = null
  confirmingDeleteId.value = asset.id
}

async function deleteAsset(asset: MediaAsset) {
  if (deleting.value) return
  deleting.value = true
  try {
    await api.deleteAsset(asset.id)
    confirmingDeleteId.value = null
    if (selectedId.value === asset.id) selectedId.value = null
    setNotice(`「${asset.original_name}」已从素材库删除。`, 'success')
    await loadAssets()
  } catch (error) {
    setNotice(errorMessage(error, '删除失败。若素材正被草稿使用，请先替换或删除对应草稿。'), 'error')
  } finally {
    deleting.value = false
  }
}

function markPreviewFailed(id: number) {
  failedPreviews.value = new Set([...failedPreviews.value, id])
}

onMounted(() => {
  void loadAssets()
  void loadCapabilities()
})
</script>

<template>
  <section class="media-library" aria-labelledby="media-library-title">
    <header class="library-heading">
      <div class="library-heading-copy">
        <div class="eyebrow"><span>STAGE 04</span><i></i><span>MEDIA LIBRARY</span></div>
        <h1 id="media-library-title">让每一份素材，都有去处。</h1>
        <p>图片与视频统一留在本机。筛选、整理，然后交给内容编辑器。</p>
      </div>
      <div class="local-seal" aria-label="素材存储在本机">
        <HardDrive :size="19" aria-hidden="true" />
        <span>LOCAL FIRST<small>本地素材库</small></span>
      </div>
    </header>

    <div class="library-toolbar">
      <nav class="kind-tabs" aria-label="素材类型">
        <button type="button" :class="{ active: activeKind === 'all' }" :aria-pressed="activeKind === 'all'" @click="setKind('all')">全部</button>
        <button type="button" :class="{ active: activeKind === 'image' }" :aria-pressed="activeKind === 'image'" @click="setKind('image')"><ImageIcon :size="15" aria-hidden="true" />图片</button>
        <button type="button" :class="{ active: activeKind === 'video' }" :aria-pressed="activeKind === 'video'" @click="setKind('video')"><Film :size="15" aria-hidden="true" />视频</button>
      </nav>
      <div class="random-controls">
        <label class="visually-hidden" for="random-kind">随机选取的素材类型</label>
        <select id="random-kind" v-model="randomKind" :disabled="randomizing">
          <option value="image">随机图片</option>
          <option value="video">随机视频</option>
        </select>
        <button class="button secondary small" type="button" :disabled="randomizing || loading" @click="pickRandom">
          <LoaderCircle v-if="randomizing" class="spin" :size="14" aria-hidden="true" />
          <Shuffle v-else :size="14" aria-hidden="true" />
          {{ randomizing ? '选取中…' : '随机抽取' }}
        </button>
      </div>
    </div>

    <form class="filter-bar" role="search" @submit.prevent="applyFilters">
      <label class="search-field">
        <Search :size="16" aria-hidden="true" />
        <span class="visually-hidden">搜索文件名或标签</span>
        <input v-model="queryDraft" type="search" placeholder="搜索文件名或标签" autocomplete="off" />
      </label>
      <label class="tag-filter">
        <Tag :size="15" aria-hidden="true" />
        <span class="visually-hidden">按标签筛选</span>
        <input v-model="tagDraft" list="media-known-tags" placeholder="按标签筛选" autocomplete="off" />
        <datalist id="media-known-tags"><option v-for="tag in knownTags" :key="tag" :value="tag" /></datalist>
      </label>
      <button class="button primary small" type="submit" :disabled="loading">应用筛选</button>
      <button v-if="appliedQuery || appliedTag" class="clear-filter" type="button" @click="clearFilters"><X :size="13" aria-hidden="true" />清除</button>
    </form>

    <div v-if="notice" class="notice" :class="noticeTone" :role="noticeTone === 'error' ? 'alert' : 'status'">
      <AlertCircle v-if="noticeTone === 'error'" :size="16" aria-hidden="true" />
      <Check v-else :size="16" aria-hidden="true" />
      <span>{{ notice }}</span>
      <button type="button" aria-label="关闭提示" @click="notice = ''"><X :size="15" aria-hidden="true" /></button>
    </div>

    <div class="library-layout">
      <div class="collection" :aria-busy="loading">
        <div class="collection-heading">
          <div><span class="section-index">M</span><h2>素材阅览</h2><span class="result-count">{{ loading ? '读取中' : resultSummary }}</span></div>
          <button class="refresh-button" type="button" :disabled="loading" @click="loadAssets"><RefreshCw :size="14" :class="{ spin: loading }" aria-hidden="true" />刷新</button>
        </div>

        <div v-if="loadError" class="state-panel error-state" role="alert">
          <AlertCircle :size="28" aria-hidden="true" />
          <h3>暂时无法读取素材</h3>
          <p>{{ loadError }}</p>
          <button class="button secondary small" type="button" @click="loadAssets"><RefreshCw :size="14" aria-hidden="true" />重新加载</button>
        </div>
        <div v-else-if="loading" class="loading-list" role="status" aria-label="正在加载素材">
          <div v-for="row in 4" :key="row" class="loading-row" aria-hidden="true"><span class="skeleton preview-skeleton"></span><span class="skeleton-copy"><i class="skeleton"></i><i class="skeleton short"></i><i class="skeleton shorter"></i></span></div>
          <span class="visually-hidden">正在加载素材，请稍候。</span>
        </div>
        <div v-else-if="!assets.length" class="state-panel empty-state">
          <span class="empty-monogram"><ImageIcon :size="29" aria-hidden="true" /></span>
          <h3>{{ appliedQuery || appliedTag ? '没有符合条件的素材' : '素材库还是空的' }}</h3>
          <p>{{ appliedQuery || appliedTag ? '换一个关键词或标签，也可以清除筛选条件。' : '从右侧上传第一张图片或第一段视频，内容会安全保存在本机。' }}</p>
          <button v-if="appliedQuery || appliedTag" class="button secondary small" type="button" @click="clearFilters">清除筛选</button>
        </div>

        <div v-else id="media-assets-panel" class="asset-list">
          <article v-for="asset in assets" :key="asset.id" class="asset-row" :class="{ selected: selectedId === asset.id }">
            <div class="asset-preview">
              <template v-if="asset.kind === 'image' && !failedPreviews.has(asset.id)">
                <img :src="asset.url" :alt="asset.original_name" loading="lazy" decoding="async" @error="markPreviewFailed(asset.id)" />
              </template>
              <video v-else-if="asset.kind === 'video' && !failedPreviews.has(asset.id)" :src="asset.url" controls playsinline preload="metadata" :aria-label="`预览视频 ${asset.original_name}`" @error="markPreviewFailed(asset.id)"></video>
              <span v-else class="preview-fallback"><ImageIcon v-if="asset.kind === 'image'" :size="25" aria-hidden="true" /><Film v-else :size="25" aria-hidden="true" /><small>预览不可用</small></span>
              <span class="kind-stamp">{{ asset.kind === 'image' ? 'IMG' : 'VID' }}</span>
              <button class="preview-select" type="button" :aria-label="`选择素材 ${asset.original_name}`" :aria-pressed="selectedId === asset.id" @click="selectAsset(asset)"><Check :size="12" aria-hidden="true" /></button>
            </div>

            <div class="asset-copy">
              <div class="asset-name-line"><h3 :title="asset.original_name">{{ asset.original_name }}</h3><span class="source-label">{{ sourceLabel(asset.source) }}</span></div>
              <p class="asset-meta"><span>{{ dimensions(asset) }}</span><span v-if="asset.kind === 'video'">{{ formatDuration(asset.duration) }}</span><span>{{ formatBytes(asset.size_bytes) }}</span></p>
              <div v-if="asset.tags.length" class="asset-tags" aria-label="素材标签"><button v-for="tag in asset.tags" :key="tag" type="button" :title="`按标签「${tag}」筛选`" @click="filterByTag(tag)"># {{ tag }}</button></div>
              <p v-else class="no-tags">尚未添加标签</p>

              <form v-if="editingId === asset.id" class="inline-tag-editor" @submit.prevent="saveTags(asset)">
                <label :for="`asset-tags-${asset.id}`">编辑标签<small>用逗号分隔</small></label>
                <div class="tag-editor-line">
                  <input :id="`asset-tags-${asset.id}`" v-model="editingTags" type="text" placeholder="例如：封面，旅行" :disabled="savingTags" autofocus />
                  <button class="button primary small" type="submit" :disabled="savingTags"><LoaderCircle v-if="savingTags" class="spin" :size="13" aria-hidden="true" /><Check v-else :size="13" aria-hidden="true" />保存</button>
                  <button class="button secondary small" type="button" :disabled="savingTags" @click="cancelTagEdit">取消</button>
                </div>
              </form>

              <div v-if="confirmingDeleteId === asset.id" class="delete-confirm" role="alert">
                <p><strong>确认删除这份素材？</strong><span>文件会从本机移除；正被草稿使用的素材无法删除。</span></p>
                <div><button class="button danger small" type="button" :disabled="deleting" @click="deleteAsset(asset)"><LoaderCircle v-if="deleting" class="spin" :size="13" aria-hidden="true" />确认删除</button><button class="button secondary small" type="button" :disabled="deleting" @click="confirmingDeleteId = null">保留</button></div>
              </div>
            </div>

            <div class="asset-actions">
              <button class="button primary small" type="button" @click="useAsset(asset)">{{ asset.kind === 'image' ? '使用图片' : '使用视频' }}<ArrowUpRight :size="13" aria-hidden="true" /></button>
              <div class="asset-secondary-actions">
                <button type="button" :aria-label="`编辑 ${asset.original_name} 的标签`" @click="beginTagEdit(asset)"><Tag :size="14" aria-hidden="true" />标签</button>
                <button class="delete-action" type="button" :aria-label="`删除 ${asset.original_name}`" @click="askDelete(asset)"><Trash2 :size="14" aria-hidden="true" />删除</button>
              </div>
            </div>
          </article>
        </div>
        <p v-if="!loading && assets.length" class="collection-footnote">选择素材后可编辑标签。点击“使用”会将素材交回上级编辑流程，不会自动发布。</p>
      </div>

      <aside class="import-rail" aria-label="导入与生成素材">
        <section class="import-section" aria-labelledby="image-import-title">
          <div class="rail-heading"><span class="section-index">01</span><div><h2 id="image-import-title">上传图片</h2><p>JPG、PNG 或 WebP，最大 {{ maxImageMb }} MB</p></div></div>
          <label for="image-upload-tags">标签<small>可选，用逗号分隔</small></label>
          <input id="image-upload-tags" v-model="imageTags" type="text" placeholder="例如：封面，教程" :disabled="uploadingImage" />
          <input ref="imageInput" class="visually-hidden-file" type="file" :accept="imageAccept" :disabled="uploadingImage" @change="uploadImage" />
          <button class="upload-button" type="button" :disabled="uploadingImage" @click="imageInput?.click()"><LoaderCircle v-if="uploadingImage" class="spin" :size="18" aria-hidden="true" /><Upload v-else :size="18" aria-hidden="true" /><span>{{ uploadingImage ? '正在保存到本机…' : '选择图片上传' }}</span></button>
        </section>

        <section class="import-section" aria-labelledby="video-import-title">
          <div class="rail-heading"><span class="section-index">02</span><div><h2 id="video-import-title">上传视频</h2><p>上传后自动校验并登记到素材库</p></div></div>
          <p class="video-note">支持 MP4、MOV、WebM、MKV、M4V。视频默认带有“视频”标签，上传后可修改。</p>
          <input ref="videoInput" class="visually-hidden-file" type="file" :accept="VIDEO_ACCEPT" :disabled="uploadingVideo" @change="uploadVideo" />
          <button class="upload-button" type="button" :disabled="uploadingVideo" @click="videoInput?.click()"><LoaderCircle v-if="uploadingVideo" class="spin" :size="18" aria-hidden="true" /><Film v-else :size="18" aria-hidden="true" /><span>{{ uploadingVideo ? '正在上传与校验…' : '选择视频上传' }}</span></button>
        </section>

        <section class="generation-section" aria-labelledby="generation-title">
          <div class="rail-heading"><span class="section-index">03</span><div><h2 id="generation-title">AI 生成图片</h2><p>按描述生成一张原创配图</p></div><WandSparkles :size="17" aria-hidden="true" /></div>
          <template v-if="capabilities?.image_generation_configured">
            <form @submit.prevent="generateImage">
              <label for="generation-prompt">画面描述</label>
              <textarea id="generation-prompt" v-model="generationPrompt" rows="4" maxlength="2000" placeholder="描述主体、氛围、构图与色彩…" :disabled="generating" required></textarea>
              <label for="generation-tags">标签<small>可选</small></label>
              <input id="generation-tags" v-model="generationTags" type="text" placeholder="例如：配图，自然光" :disabled="generating" />
              <button class="button primary full-width" type="submit" :disabled="generating || !generationPrompt.trim()"><LoaderCircle v-if="generating" class="spin" :size="15" aria-hidden="true" /><WandSparkles v-else :size="15" aria-hidden="true" />{{ generating ? '正在生成并入库…' : '生成并保存' }}</button>
            </form>
            <p class="generation-note">生成结果会保存到本地，并自动添加“AI生成”标签。</p>
          </template>
          <div v-else class="generation-unavailable">
            <p><strong>{{ capabilities ? 'AI 生图尚未配置' : '正在检查生图能力' }}</strong><span>{{ capabilitiesError || '在项目 .env 中设置 IMAGE_BASE_URL、IMAGE_API_KEY 和 IMAGE_MODEL 后即可使用。本机图片上传不受影响。' }}</span></p>
            <button v-if="capabilitiesError" class="text-button" type="button" @click="loadCapabilities"><RefreshCw :size="13" aria-hidden="true" />重试检查</button>
          </div>
        </section>
        <p class="privacy-note"><HardDrive :size="13" aria-hidden="true" />上传与生成仅连接你配置的本地服务；不会操作发布账号。</p>
      </aside>
    </div>
    <span v-if="selectedAsset" class="visually-hidden" role="status">已选择 {{ selectedAsset.original_name }}</span>
  </section>
</template>

<style scoped>
.media-library {
  --ml-paper: #eee9df;
  --ml-paper-light: #f8f5ee;
  --ml-ink: #292923;
  --ml-muted: #827b6e;
  --ml-line: #d7cfc1;
  --ml-red: #a44732;
  min-width: 0;
  max-width: 1480px;
  margin: 0 auto;
  padding: clamp(24px, 3vw, 42px);
  color: var(--ml-ink);
  overflow-wrap: anywhere;
}
.media-library *, .media-library *::before, .media-library *::after { box-sizing: border-box; }
.media-library button, .media-library input, .media-library textarea, .media-library select { font: inherit; }
.media-library button { color: inherit; cursor: pointer; }
.media-library button:disabled { cursor: not-allowed; opacity: .48; }
.media-library button:focus-visible, .media-library input:focus-visible, .media-library textarea:focus-visible, .media-library select:focus-visible {
  outline: 2px solid var(--ml-red);
  outline-offset: 3px;
}
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.library-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 30px; }
.library-heading-copy { min-width: 0; }
.eyebrow { display: flex; align-items: center; gap: 10px; color: var(--ml-red); font-family: Georgia, serif; font-size: 9px; letter-spacing: 2.2px; }
.eyebrow i { width: 25px; height: 1px; background: #a447326b; }
.library-heading h1 { margin: 13px 0 10px; font-family: 'Noto Serif SC', 'Songti SC', 'STSong', serif; font-size: clamp(28px, 3.2vw, 43px); font-weight: 600; line-height: 1.32; letter-spacing: -.055em; }
.library-heading p { margin: 0; color: var(--ml-muted); font-size: 12px; line-height: 1.8; }
.local-seal { flex: 0 0 auto; display: flex; align-items: center; gap: 10px; padding: 10px 13px; border: 1px solid #cfc5b5; color: #7b715f; }
.local-seal > span { display: flex; flex-direction: column; gap: 4px; font-family: Georgia, serif; font-size: 8px; letter-spacing: 1.3px; }
.local-seal small { font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 9px; letter-spacing: .4px; }
.library-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding: 11px 0; border-top: 1px solid var(--ml-line); border-bottom: 1px solid var(--ml-line); }
.kind-tabs { display: flex; align-items: center; gap: 4px; }
.kind-tabs button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 35px; border: 1px solid transparent; border-radius: 2px; padding: 7px 15px; background: transparent; color: #7b7264; font-size: 11px; }
.kind-tabs button:hover { background: #e5ded2; }
.kind-tabs button.active { border-color: #a4473252; background: #a4473209; color: var(--ml-red); }
.random-controls { display: flex; align-items: center; gap: 7px; }
.random-controls select { height: 33px; max-width: 105px; border: 1px solid #d4ccbd; border-radius: 2px; padding: 0 6px; background: var(--ml-paper-light); color: #6e6558; font-size: 10px; }
.button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; border: 1px solid transparent; border-radius: 2px; padding: 9px 14px; font-size: 11px; font-weight: 500; transition: background .18s, border-color .18s; }
.button.primary { border-color: var(--ml-red); background: var(--ml-red); color: #fff9ef; }
.button.primary:hover:not(:disabled) { border-color: #853622; background: #853622; }
.button.secondary { border-color: #d4ccbd; background: #f7f3ea; color: #655c4e; }
.button.secondary:hover:not(:disabled) { border-color: #aaa08f; background: #fffaf1; }
.button.danger { border-color: #a44732; background: transparent; color: #953e2d; }
.button.danger:hover:not(:disabled) { background: #a4473210; }
.button.small { min-height: 33px; padding: 7px 10px; font-size: 10px; }
.full-width { width: 100%; }
.filter-bar { display: flex; align-items: center; gap: 8px; padding: 15px 0; }
.search-field, .tag-filter { min-width: 0; height: 38px; display: flex; align-items: center; gap: 8px; border: 1px solid #d7cfc1; background: #f6f2e9; padding: 0 11px; color: #9b9181; }
.search-field { flex: 1 1 240px; }
.tag-filter { flex: 0 1 210px; }
.search-field:focus-within, .tag-filter:focus-within { border-color: #a4473280; }
.search-field input, .tag-filter input { min-width: 0; width: 100%; height: 100%; border: 0; outline: 0; background: transparent; color: var(--ml-ink); font-size: 11px; }
.search-field input::placeholder, .tag-filter input::placeholder { color: #a3998a; }
.clear-filter, .refresh-button, .text-button { display: inline-flex; align-items: center; gap: 4px; border: 0; padding: 5px; background: transparent; color: #8c5e49; font-size: 10px; }
.clear-filter:hover, .refresh-button:hover, .text-button:hover { color: #713421; text-decoration: underline; text-underline-offset: 3px; }
.notice { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 16px; border-left: 2px solid #7e8c70; padding: 10px 12px; background: #e7eadf; color: #4d6348; font-size: 11px; line-height: 1.7; }
.notice.error { border-color: var(--ml-red); background: #f0e2d8; color: #86412f; }
.notice > span { flex: 1; min-width: 0; }
.notice > svg { flex: 0 0 auto; margin-top: 2px; }
.notice button { display: grid; place-items: center; flex: 0 0 auto; width: 24px; height: 24px; border: 0; background: transparent; color: inherit; }
.library-layout { display: grid; grid-template-columns: minmax(0, 1fr) 292px; gap: clamp(22px, 3vw, 38px); align-items: start; }
.collection { min-width: 0; }
.collection-heading { min-height: 44px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--ml-ink); }
.collection-heading > div { display: flex; align-items: center; gap: 9px; min-width: 0; }
.section-index { width: 20px; height: 20px; flex: 0 0 auto; display: grid; place-items: center; border: 1px solid #cfc6b7; color: #8b8172; font-family: Georgia, serif; font-size: 9px; }
.collection-heading h2, .rail-heading h2 { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: .2px; }
.result-count { color: #958b7c; font-size: 9px; }
.state-panel { min-height: 340px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 35px 20px; border-bottom: 1px solid var(--ml-line); text-align: center; color: #968b7a; }
.state-panel h3 { margin: 20px 0 8px; color: #665d50; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 18px; font-weight: 500; }
.state-panel p { max-width: 390px; margin: 0 0 18px; font-size: 11px; line-height: 1.9; }
.empty-monogram { width: 68px; height: 78px; display: grid; place-items: center; border: 1px solid #bcb2a2; background: #e8e1d480; color: #9f9180; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 30px; }
.error-state > svg { color: var(--ml-red); }
.loading-list { min-height: 340px; }
.loading-row { display: grid; grid-template-columns: 135px minmax(0, 1fr); gap: 18px; padding: 18px 0; border-bottom: 1px solid var(--ml-line); }
.skeleton { display: block; height: 10px; background: #ddd5c7; animation: pulse 1.4s ease-in-out infinite alternate; }
.preview-skeleton { height: 100px; }
.skeleton-copy { display: flex; flex-direction: column; justify-content: center; gap: 14px; }
.skeleton-copy i { width: 65%; }
.skeleton-copy i.short { width: 43%; }
.skeleton-copy i.shorter { width: 28%; }
.asset-list { border-bottom: 1px solid var(--ml-ink); }
.asset-row { position: relative; display: grid; grid-template-columns: 135px minmax(0, 1fr) auto; gap: 17px; align-items: center; padding: 18px 0; border-bottom: 1px solid var(--ml-line); transition: background .18s; }
.asset-row:last-child { border-bottom: 0; }
.asset-row.selected { background: #a4473207; }
.asset-row.selected::before { content: ''; position: absolute; inset: 12px auto 12px -10px; width: 2px; background: var(--ml-red); }
.asset-preview { position: relative; width: 135px; aspect-ratio: 4 / 3; display: block; overflow: hidden; border: 1px solid #cfc5b6; padding: 0; background: #ded6c9; color: #8f8372; }
.asset-preview img, .asset-preview video { width: 100%; height: 100%; display: block; object-fit: cover; }
.asset-preview video { object-fit: contain; background: #272720; }
.asset-preview:hover { border-color: #a4473280; }
.kind-stamp { position: absolute; top: 6px; left: 6px; padding: 3px 5px; border: 1px solid #eee9df66; background: #292923c9; color: #f5f0e5; font-family: Georgia, serif; font-size: 7px; letter-spacing: 1px; pointer-events: none; }
.preview-select { position: absolute; top: 5px; right: 5px; width: 25px; height: 25px; display: grid; place-items: center; border: 1px solid #eee9df66; border-radius: 2px; padding: 0; background: #292923a8; color: transparent; }
.preview-select:hover, .preview-select[aria-pressed='true'] { background: var(--ml-red); color: #fff9ef; }
.preview-select:focus-visible { outline-offset: 2px; }
.preview-fallback { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; }
.preview-fallback small { font-size: 8px; }
.asset-copy { min-width: 0; align-self: center; }
.asset-name-line { display: flex; align-items: baseline; flex-wrap: wrap; gap: 7px; }
.asset-name-line h3 { min-width: 0; max-width: 100%; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 14px; font-weight: 600; }
.source-label { flex: 0 0 auto; padding: 2px 5px; border: 1px solid #d5ccbe; color: #8e8373; font-size: 8px; }
.asset-meta { display: flex; flex-wrap: wrap; gap: 0; margin: 8px 0; color: #958b7c; font-size: 9px; }
.asset-meta span + span::before { content: '·'; margin: 0 7px; color: #b0a595; }
.asset-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.asset-tags button { max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border: 0; border-radius: 2px; padding: 3px 5px; background: #e5ded2; color: #7a6f60; font-size: 8px; }
.asset-tags button:hover { background: #ddd3c4; color: var(--ml-red); }
.no-tags { margin: 0; color: #aca292; font-size: 9px; }
.asset-actions { min-width: 95px; display: flex; flex-direction: column; align-items: stretch; gap: 9px; }
.asset-secondary-actions { display: flex; justify-content: center; gap: 10px; }
.asset-secondary-actions button { display: inline-flex; align-items: center; gap: 4px; border: 0; padding: 3px 0; background: transparent; color: #8a8071; font-size: 9px; }
.asset-secondary-actions button:hover { color: var(--ml-red); }
.asset-secondary-actions .delete-action:hover { color: #a44732; }
.inline-tag-editor { margin-top: 12px; padding-top: 11px; border-top: 1px dashed #d2c8b8; }
.inline-tag-editor > label, .import-rail label { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 6px; color: #776d5e; font-size: 10px; }
.inline-tag-editor label small, .import-rail label small { color: #a19686; font-size: 8px; font-weight: 400; }
.tag-editor-line { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-editor-line input { min-width: 120px; flex: 1 1 150px; height: 33px; border: 1px solid #d3c9ba; border-radius: 2px; padding: 0 9px; background: #fbf8f1; color: var(--ml-ink); font-size: 10px; }
.delete-confirm { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 9px; margin-top: 12px; border-left: 2px solid var(--ml-red); padding: 9px 10px; background: #efe2d8; }
.delete-confirm p { display: flex; flex-direction: column; gap: 4px; min-width: 150px; flex: 1; margin: 0; color: #854634; font-size: 9px; line-height: 1.6; }
.delete-confirm p strong { font-size: 10px; font-weight: 600; }
.delete-confirm > div { display: flex; gap: 5px; }
.collection-footnote { margin: 12px 0 0; color: #9b9182; font-size: 9px; line-height: 1.8; }
.import-rail { min-width: 0; border-top: 1px solid var(--ml-ink); }
.import-section, .generation-section { padding: 19px 0 21px; border-bottom: 1px solid var(--ml-line); }
.rail-heading { display: flex; align-items: flex-start; gap: 9px; margin-bottom: 16px; }
.rail-heading > div { min-width: 0; }
.rail-heading p { margin: 5px 0 0; color: #9a9081; font-size: 9px; line-height: 1.6; }
.rail-heading > svg { margin-left: auto; color: #a4473294; }
.import-rail input:not([type='file']), .import-rail textarea { width: 100%; border: 1px solid #d5ccbe; border-radius: 2px; padding: 9px 10px; background: #f7f3eb; color: var(--ml-ink); font-size: 11px; line-height: 1.6; }
.import-rail textarea { min-height: 92px; resize: vertical; }
.import-rail input::placeholder, .import-rail textarea::placeholder { color: #aca292; }
.visually-hidden-file { position: absolute; width: 1px; height: 1px; overflow: hidden; opacity: 0; pointer-events: none; }
.upload-button { width: 100%; min-height: 43px; display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 11px; border: 1px dashed #b9ad9b; border-radius: 2px; background: #e8e1d580; color: #756a5a; font-size: 11px; }
.upload-button:hover:not(:disabled) { border-color: #a4473280; background: #a4473208; color: var(--ml-red); }
.video-note { margin: 0 0 11px; color: #928777; font-size: 9px; line-height: 1.8; }
.generation-section form > label { margin-top: 11px; }
.generation-section form > .button { margin-top: 13px; }
.generation-note { margin: 9px 0 0; color: #9d9282; font-size: 8px; line-height: 1.7; }
.generation-unavailable { border-left: 2px solid #c5b9a7; padding: 1px 0 1px 10px; }
.generation-unavailable p { display: flex; flex-direction: column; gap: 6px; margin: 0; color: #928674; font-size: 9px; line-height: 1.8; }
.generation-unavailable strong { color: #766b5b; font-size: 10px; font-weight: 500; }
.generation-unavailable .text-button { margin-top: 8px; }
.privacy-note { display: flex; align-items: flex-start; gap: 6px; margin: 14px 0 0; color: #9c9282; font-size: 8px; line-height: 1.8; }
.privacy-note svg { flex: 0 0 auto; margin-top: 2px; }
.spin { animation: ml-spin .9s linear infinite; }
@keyframes ml-spin { to { transform: rotate(360deg); } }
@keyframes ml-pulse { to { opacity: .45; } }
@media (max-width: 1120px) {
  .library-layout { grid-template-columns: minmax(0, 1fr) 260px; gap: 24px; }
  .asset-row { grid-template-columns: 112px minmax(0, 1fr); }
  .asset-preview { width: 112px; }
  .asset-actions { grid-column: 2; min-width: 0; flex-direction: row; align-items: center; justify-content: flex-start; }
}
@media (max-width: 900px) {
  .media-library { padding: 26px 24px 40px; }
  .library-layout { grid-template-columns: minmax(0, 1fr); }
  .import-rail { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 24px; border-top: 0; }
  .generation-section { grid-column: 1 / -1; }
  .privacy-note { grid-column: 1 / -1; }
  .asset-row { grid-template-columns: 135px minmax(0, 1fr) auto; }
  .asset-preview { width: 135px; }
  .asset-actions { grid-column: auto; flex-direction: column; align-items: stretch; }
}
@media (max-width: 650px) {
  .media-library { padding: 23px 16px 36px; }
  .library-heading { align-items: flex-start; margin-bottom: 23px; }
  .library-heading h1 { font-size: clamp(27px, 7.8vw, 36px); }
  .local-seal { display: none; }
  .library-toolbar { align-items: flex-start; flex-direction: column; }
  .kind-tabs { width: 100%; }
  .kind-tabs button { flex: 1; padding-inline: 8px; }
  .random-controls { width: 100%; justify-content: flex-end; }
  .filter-bar { flex-wrap: wrap; }
  .search-field { flex-basis: 100%; }
  .tag-filter { flex: 1 1 140px; }
  .import-rail { grid-template-columns: minmax(0, 1fr); }
  .generation-section, .privacy-note { grid-column: auto; }
  .asset-row { grid-template-columns: 92px minmax(0, 1fr); gap: 12px; align-items: start; }
  .asset-preview { width: 92px; }
  .asset-name-line h3 { font-size: 13px; white-space: normal; line-height: 1.5; }
  .asset-actions { grid-column: 1 / -1; flex-direction: row; align-items: center; justify-content: space-between; padding-top: 9px; border-top: 1px dashed #d8cfc1; }
  .asset-secondary-actions { gap: 15px; }
  .asset-row.selected::before { inset: 10px auto 10px -7px; }
  .loading-row { grid-template-columns: 92px minmax(0, 1fr); gap: 12px; }
  .preview-skeleton { height: 72px; }
  .tag-editor-line .button { flex: 1; }
  .delete-confirm { align-items: stretch; flex-direction: column; }
  .delete-confirm > div { justify-content: flex-end; }
  .collection-heading { flex-wrap: wrap; padding-bottom: 8px; }
}
@media (max-width: 390px) {
  .media-library { padding-inline: 13px; }
  .eyebrow { font-size: 8px; letter-spacing: 1.6px; }
  .library-heading p { font-size: 11px; }
  .filter-bar > .button { padding-inline: 9px; }
  .result-count { font-size: 8px; }
  .asset-row { grid-template-columns: 82px minmax(0, 1fr); gap: 10px; }
  .asset-preview { width: 82px; }
  .source-label { font-size: 7px; }
  .asset-meta { font-size: 8px; }
  .asset-meta span + span::before { margin-inline: 5px; }
}
@media (prefers-reduced-motion: reduce) {
  .media-library *, .media-library *::before, .media-library *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
</style>
