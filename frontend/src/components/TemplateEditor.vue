<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import {
  AlertCircle, ArrowUpRight, BookOpenText, Check, Copy, HardDrive, LayoutTemplate,
  LoaderCircle, LockKeyhole, PenLine, Plus, RefreshCw, Save, Trash2, X,
} from 'lucide-vue-next'
import { api } from '../api'
import type { Preset, Preview } from '../types'

defineOptions({ name: 'TemplateEditor' })

const props = defineProps<{ presets: Preset[] }>()
const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'apply', preset: Preset): void
}>()

type PlatformHint = 'wechat' | 'zhihu' | 'general'
type TemplateDraft = {
  id: string | null
  name: string
  description: string
  platform_hint: PlatformHint
  style: Preset['style']
}

const FONT_OPTIONS = [
  { value: "'Noto Serif SC','Songti SC',serif", label: '宋体 / 思源宋体' },
  { value: "'Noto Sans SC','Microsoft YaHei',sans-serif", label: '黑体 / 思源黑体' },
  { value: "'KaiTi','STKaiti',serif", label: '楷体' },
  { value: "Georgia,'Times New Roman',serif", label: 'Georgia / 衬线' },
]
const ACCENT_SWATCHES = ['#a44732', '#315d70', '#4f7258', '#9a6b35']
const SAMPLE_TITLE = '把日常写成值得停留的文字'
const SAMPLE_COVER = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">'
  + '<rect width="1200" height="630" fill="#e8e1d5"/>'
  + '<path d="M0 500L420 170l280 330 180-210 320 340v90H0z" fill="#d5cbbb"/>'
  + '<circle cx="866" cy="202" r="112" fill="#a44732"/>'
  + '<path d="M110 146h310M110 174h190" stroke="#292923" stroke-width="3"/>'
  + '<text x="110" y="260" fill="#292923" font-family="Georgia,serif" font-size="38" letter-spacing="8">PUBLISHFLOW / FIELD NOTES</text>'
  + '</svg>',
)}`
const SAMPLE_BODY = `## 从一个小小的观察开始

好的文字不急着给出结论。它先停下来，看看光怎样落在桌面上，听一听街角店铺开门的声音。

> 写作是把熟悉的生活，重新看得仔细一点。

## 让段落有呼吸

短句适合放下判断，长句适合容纳经验。留白不是空着，而是给读者留下回应的位置。

- 用一个具体的场景开场
- 把观点放进真实的故事
- 在结尾留下一点余味`

const DEFAULT_STYLE: Preset['style'] = {
  fontFamily: FONT_OPTIONS[0].value,
  fontSize: 16,
  lineHeight: 1.9,
  paragraphSpacing: 18,
  accent: '#a44732',
  headingStyle: 'left-border',
  quoteStyle: 'paper',
  firstImageRule: 'cover',
  tailText: '感谢阅读，愿每一次表达都有回响。',
}

function emptyDraft(): TemplateDraft {
  return {
    id: null,
    name: '',
    description: '',
    platform_hint: 'general',
    style: { ...DEFAULT_STYLE },
  }
}

function platformHint(value: string): PlatformHint {
  return value === 'wechat' || value === 'zhihu' ? value : 'general'
}

function draftFromPreset(preset: Preset): TemplateDraft {
  return {
    id: preset.id,
    name: preset.name,
    description: preset.description,
    platform_hint: platformHint(preset.platform_hint),
    style: { ...preset.style },
  }
}

function snapshot(draft: TemplateDraft) {
  return JSON.stringify(draft)
}

const draft = ref<TemplateDraft>(emptyDraft())
const savedSnapshot = ref('')
const savedPreset = ref<Preset | null>(null)
const initialized = ref(false)
const actionError = ref('')
const notice = ref('')
const saving = ref(false)
const deleting = ref(false)
const deleteCandidate = ref<Preset | null>(null)
const deleteCancelButton = ref<HTMLButtonElement | null>(null)

const builtinPresets = computed(() => props.presets.filter((preset) => preset.is_builtin))
const customPresets = computed(() => props.presets.filter((preset) => !preset.is_builtin))
const currentPreset = computed(() => {
  if (!draft.value.id) return null
  return props.presets.find((preset) => preset.id === draft.value.id)
    ?? (savedPreset.value?.id === draft.value.id ? savedPreset.value : null)
})
const isBuiltin = computed(() => Boolean(currentPreset.value?.is_builtin))
const isDirty = computed(() => snapshot(draft.value) !== savedSnapshot.value)
const canApply = computed(() => Boolean(currentPreset.value && !isDirty.value && !saving.value && !deleting.value))
const modeLabel = computed(() => {
  if (isBuiltin.value) return '内置 · 只读'
  if (!draft.value.id) return '新建自定义'
  return '自定义编辑'
})
const unknownFont = computed(() => (
  draft.value.style.fontFamily && !FONT_OPTIONS.some((font) => font.value === draft.value.style.fontFamily)
))
const nameInvalid = computed(() => Boolean(actionError.value) && !draft.value.name.trim())
const platformLabel = (value: string) => ({ wechat: '公众号', zhihu: '知乎', general: '通用' })[value] || value

function clearActionError() {
  actionError.value = ''
}

function clearFeedback() {
  actionError.value = ''
  notice.value = ''
}

watch(draft, clearFeedback, { deep: true, flush: 'sync' })

function loadPreset(preset: Preset) {
  draft.value = draftFromPreset(preset)
  savedSnapshot.value = snapshot(draft.value)
  savedPreset.value = preset
  deleteCandidate.value = null
  clearFeedback()
}

function newTemplate() {
  initialized.value = true
  draft.value = emptyDraft()
  savedSnapshot.value = ''
  savedPreset.value = null
  deleteCandidate.value = null
  clearFeedback()
}

function copyPreset(preset: Preset) {
  if (!preset.is_builtin) return
  initialized.value = true
  draft.value = {
    ...draftFromPreset(preset),
    id: null,
    name: `${preset.name} 副本`.slice(0, 100),
  }
  savedSnapshot.value = ''
  savedPreset.value = null
  deleteCandidate.value = null
  clearFeedback()
  notice.value = '已复制为自定义草稿，调整后即可保存。'
}

watch(() => props.presets, (presets) => {
  if (!presets.length) return
  if (!initialized.value) {
    initialized.value = true
    loadPreset(presets.find((preset) => preset.id === 'fresh') ?? presets[0])
    return
  }
  if (!draft.value.id || isDirty.value) return
  const current = presets.find((preset) => preset.id === draft.value.id)
  if (current) {
    const feedback = notice.value
    loadPreset(current)
    notice.value = feedback
  } else if (savedPreset.value?.id !== draft.value.id) {
    loadPreset(presets[0])
  }
}, { immediate: true })

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

function payload() {
  return {
    name: draft.value.name.trim(),
    description: draft.value.description.trim(),
    platform_hint: draft.value.platform_hint,
    style: { ...draft.value.style },
  }
}

function validate() {
  const { name, description, style } = draft.value
  if (!name.trim()) return '请先填写模板名称。'
  if (name.trim().length > 100) return '模板名称不能超过 100 个字符。'
  if (description.length > 300) return '模板说明不能超过 300 个字符。'
  if (!style.fontFamily.trim() || style.fontFamily.length > 120 || !/^[\w\s,'"-]+$/.test(style.fontFamily)) {
    return '请选择有效的字体；自定义字体名称仅可包含字母、数字、空格、引号、逗号和连字符。'
  }
  if (!Number.isInteger(style.fontSize) || style.fontSize < 12 || style.fontSize > 24) return '字号应为 12–24 之间的整数。'
  if (!Number.isFinite(style.lineHeight) || style.lineHeight < 1.2 || style.lineHeight > 2.4) return '行高应在 1.2–2.4 之间。'
  if (!Number.isInteger(style.paragraphSpacing) || style.paragraphSpacing < 6 || style.paragraphSpacing > 36) return '段间距应为 6–36 之间的整数。'
  if (!/^#[0-9a-fA-F]{6}$/.test(style.accent)) return '强调色应为六位十六进制颜色。'
  if (style.tailText.length > 200) return '尾注不能超过 200 个字符。'
  return ''
}

async function saveTemplate() {
  if (isBuiltin.value || saving.value) return
  const validationError = validate()
  if (validationError) {
    actionError.value = validationError
    return
  }
  saving.value = true
  clearActionError()
  try {
    const saved = draft.value.id
      ? await api.updatePreset(draft.value.id, payload())
      : await api.savePreset(payload())
    initialized.value = true
    loadPreset(saved)
    notice.value = '模板已保存到本机。'
    emit('saved')
  } catch (error) {
    actionError.value = errorMessage(error, '模板保存失败，请稍后重试。')
  } finally {
    saving.value = false
  }
}

function applyTemplate() {
  const preset = currentPreset.value
  if (!preset || !canApply.value) return
  clearActionError()
  emit('apply', preset)
  notice.value = `已应用「${preset.name}」。`
}

function requestDelete() {
  const preset = currentPreset.value
  if (!preset || preset.is_builtin || deleting.value) return
  clearActionError()
  deleteCandidate.value = preset
  void nextTick(() => deleteCancelButton.value?.focus())
}

function cancelDelete() {
  if (deleting.value) return
  deleteCandidate.value = null
  clearActionError()
}

async function confirmDelete() {
  const preset = deleteCandidate.value
  if (!preset || preset.is_builtin || deleting.value) return
  deleting.value = true
  clearActionError()
  try {
    await api.deletePreset(preset.id)
    deleteCandidate.value = null
    savedPreset.value = null
    newTemplate()
    notice.value = `已删除「${preset.name}」。`
    emit('saved')
  } catch (error) {
    actionError.value = errorMessage(error, '模板删除失败，请稍后重试。')
  } finally {
    deleting.value = false
  }
}

const previewHtml = ref('')
const previewStats = ref<Preview['stats'] | null>(null)
const previewError = ref('')
const previewLoading = ref(false)
let previewTimer: ReturnType<typeof setTimeout> | undefined
let previewSequence = 0

const previewDocument = computed(() => {
  if (!previewHtml.value) return ''
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
    *{box-sizing:border-box}html,body{margin:0;background:#fffdf7;color:#292923}body{padding:clamp(24px,6vw,54px);font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif}.rendered-article{max-width:720px;margin:0 auto;overflow-wrap:anywhere}.rendered-article img{max-width:100%;height:auto}.rendered-article pre{max-width:100%;overflow:auto}.rendered-article h1,.rendered-article h2,.rendered-article h3{overflow-wrap:anywhere}
  </style></head><body>${previewHtml.value}</body></html>`
})

async function fetchPreview(sequence: number) {
  previewLoading.value = true
  previewError.value = ''
  try {
    const result = await api.preview({
      title: SAMPLE_TITLE,
      body: SAMPLE_BODY,
      preset_id: 'fresh',
      cover_url: SAMPLE_COVER,
      style: { ...draft.value.style },
    })
    if (sequence !== previewSequence) return
    previewHtml.value = result.html
    previewStats.value = result.stats
  } catch (error) {
    if (sequence !== previewSequence) return
    previewError.value = errorMessage(error, '预览生成失败，请重试。')
  } finally {
    if (sequence === previewSequence) previewLoading.value = false
  }
}

function schedulePreview() {
  clearTimeout(previewTimer)
  const sequence = ++previewSequence
  previewError.value = ''
  previewLoading.value = true
  previewTimer = setTimeout(() => void fetchPreview(sequence), 450)
}

function refreshPreview() {
  clearTimeout(previewTimer)
  void fetchPreview(++previewSequence)
}

watch(() => draft.value.style, schedulePreview, { deep: true, immediate: true })

defineExpose({ canLeave: () => !isDirty.value })

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

window.addEventListener('beforeunload', handleBeforeUnload)

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  clearTimeout(previewTimer)
  previewSequence += 1
})

function formatUpdated(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)
}
</script>

<template>
  <section class="template-editor" aria-labelledby="template-editor-title">
    <header class="te-heading">
      <div>
        <div class="te-eyebrow"><span /> TYPOGRAPHY STUDIO · 05</div>
        <h2 id="template-editor-title">模板工坊</h2>
        <p>让字体、节奏与留白，成为你的固定表达。</p>
      </div>
      <button class="te-button primary" type="button" :disabled="saving || deleting" @click="newTemplate">
        <Plus :size="15" aria-hidden="true" /> 新建模板
      </button>
    </header>

    <div class="te-layout">
      <aside class="te-library" aria-labelledby="template-library-title">
        <div class="te-library-head">
          <div>
            <span class="te-section-no">01</span>
            <h3 id="template-library-title">模板库</h3>
          </div>
          <span class="te-count">{{ props.presets.length }} 份</span>
        </div>

        <div v-if="!props.presets.length" class="te-library-empty">
          <BookOpenText :size="25" aria-hidden="true" />
          <p>还没有模板。<br />从一份空白版式开始。</p>
        </div>

        <template v-if="builtinPresets.length">
          <div class="te-group-label"><span>内置模板</span><small>{{ builtinPresets.length }}</small></div>
          <div class="te-list">
            <button
              v-for="preset in builtinPresets"
              :key="preset.id"
              class="te-list-item"
              :class="{ active: draft.id === preset.id }"
              type="button"
              :disabled="saving || deleting"
              :aria-pressed="draft.id === preset.id"
              :aria-label="`查看内置模板：${preset.name}`"
              @click="loadPreset(preset)"
            >
              <span class="te-glyph" :style="{ color: preset.style.accent, fontFamily: preset.style.fontFamily }">Aa</span>
              <span class="te-item-copy">
                <span class="te-item-title">{{ preset.name }} <LockKeyhole :size="11" aria-hidden="true" /></span>
                <span class="te-item-description">{{ preset.description }}</span>
                <small>{{ platformLabel(preset.platform_hint) }} · 只读</small>
              </span>
            </button>
          </div>
        </template>

        <template v-if="customPresets.length">
          <div class="te-group-label"><span>我的模板</span><small>{{ customPresets.length }}</small></div>
          <div class="te-list">
            <button
              v-for="preset in customPresets"
              :key="preset.id"
              class="te-list-item"
              :class="{ active: draft.id === preset.id }"
              type="button"
              :disabled="saving || deleting"
              :aria-pressed="draft.id === preset.id"
              :aria-label="`编辑自定义模板：${preset.name}`"
              @click="loadPreset(preset)"
            >
              <span class="te-glyph" :style="{ color: preset.style.accent, fontFamily: preset.style.fontFamily }">Aa</span>
              <span class="te-item-copy">
                <span class="te-item-title">{{ preset.name }} <PenLine :size="11" aria-hidden="true" /></span>
                <span class="te-item-description">{{ preset.description || '尚未填写模板说明' }}</span>
                <small>{{ platformLabel(preset.platform_hint) }}<template v-if="formatUpdated(preset.updated_at)"> · {{ formatUpdated(preset.updated_at) }} 更新</template></small>
              </span>
            </button>
          </div>
        </template>

        <p class="te-library-note"><LockKeyhole :size="12" aria-hidden="true" /> 内置模板不可修改，可复制后自由调整。</p>
      </aside>

      <form class="te-form" novalidate @submit.prevent="saveTemplate">
        <div class="te-form-head">
          <div>
            <span class="te-section-no">02</span>
            <h3>{{ isBuiltin ? '查看版式' : draft.id ? '调整版式' : '创建版式' }}</h3>
          </div>
          <span class="te-mode" :class="{ readonly: isBuiltin }">
            <LockKeyhole v-if="isBuiltin" :size="11" aria-hidden="true" />
            <span v-else class="te-mode-dot" />
            {{ modeLabel }}
          </span>
        </div>

        <div v-if="isBuiltin" class="te-readonly-note">
          <LockKeyhole :size="15" aria-hidden="true" />
          <p>这是受保护的内置模板。复制为自定义模板后，即可编辑并保存。</p>
          <button class="te-inline-button" type="button" @click="copyPreset(currentPreset!)"><Copy :size="13" aria-hidden="true" /> 复制模板</button>
        </div>

        <fieldset class="te-fields" :disabled="isBuiltin || saving || deleting">
          <legend class="te-visually-hidden">模板设置</legend>

          <div class="te-field-section">
            <div class="te-field-section-title"><span>基本信息</span><small>IDENTITY</small></div>
            <label class="te-field" for="template-name">
              <span>模板名称 <b>*</b></span>
              <input
                id="template-name"
                v-model="draft.name"
                type="text"
                maxlength="100"
                required
                autocomplete="off"
                placeholder="例如：我的长文排版"
                :aria-invalid="nameInvalid || undefined"
                :aria-describedby="actionError ? 'name-error' : undefined"
              />
            </label>
            <label class="te-field" for="template-description">
              <span>模板说明</span>
              <textarea id="template-description" v-model="draft.description" rows="2" maxlength="300" placeholder="记录这份模板适合的内容与气质" />
            </label>
            <label class="te-field" for="template-platform">
              <span>平台提示</span>
              <select id="template-platform" v-model="draft.platform_hint">
                <option value="general">通用</option>
                <option value="wechat">微信公众号</option>
                <option value="zhihu">知乎</option>
              </select>
            </label>
          </div>

          <div class="te-field-section">
            <div class="te-field-section-title"><span>文字与节奏</span><small>TYPE & RHYTHM</small></div>
            <label class="te-field" for="template-font">
              <span>字体</span>
              <select id="template-font" v-model="draft.style.fontFamily">
                <option v-for="font in FONT_OPTIONS" :key="font.value" :value="font.value">{{ font.label }}</option>
                <option v-if="unknownFont" :value="draft.style.fontFamily">{{ draft.style.fontFamily }}（当前）</option>
              </select>
            </label>
            <div class="te-field-grid">
              <label class="te-field" for="template-font-size">
                <span>字号</span>
                <span class="te-number-wrap">
                  <input id="template-font-size" v-model.number="draft.style.fontSize" type="number" min="12" max="24" step="1" />
                  <small>px</small>
                </span>
              </label>
              <label class="te-field" for="template-line-height">
                <span>行高</span>
                <span class="te-number-wrap">
                  <input id="template-line-height" v-model.number="draft.style.lineHeight" type="number" min="1.2" max="2.4" step="0.05" />
                  <small>倍</small>
                </span>
              </label>
            </div>
            <label class="te-field" for="template-spacing">
              <span>段间距</span>
              <span class="te-number-wrap">
                <input id="template-spacing" v-model.number="draft.style.paragraphSpacing" type="number" min="6" max="36" step="1" />
                <small>px</small>
              </span>
            </label>
            <div class="te-field">
              <span id="accent-label">强调色</span>
              <div class="te-accent-control" role="group" aria-labelledby="accent-label">
                <input v-model="draft.style.accent" type="color" aria-label="选择强调色" />
                <output aria-live="polite">{{ draft.style.accent.toUpperCase() }}</output>
                <div class="te-swatches">
                  <button
                    v-for="color in ACCENT_SWATCHES"
                    :key="color"
                    type="button"
                    :style="{ '--swatch': color }"
                    :aria-label="`使用强调色 ${color}`"
                    :aria-pressed="draft.style.accent.toLowerCase() === color"
                    @click="draft.style.accent = color"
                  ><Check v-if="draft.style.accent.toLowerCase() === color" :size="12" aria-hidden="true" /></button>
                </div>
              </div>
            </div>
          </div>

          <div class="te-field-section">
            <div class="te-field-section-title"><span>细节规则</span><small>DETAILS</small></div>
            <label class="te-field" for="template-heading-style">
              <span>标题样式</span>
              <select id="template-heading-style" v-model="draft.style.headingStyle">
                <option value="left-border">左侧朱线</option>
                <option value="numbered">章节编号</option>
                <option value="none">纯文字</option>
              </select>
            </label>
            <label class="te-field" for="template-quote-style">
              <span>引用样式</span>
              <select id="template-quote-style" v-model="draft.style.quoteStyle">
                <option value="paper">纸色底</option>
                <option value="line">左侧细线</option>
                <option value="none">无衬底</option>
              </select>
            </label>
            <label class="te-field" for="template-image-rule">
              <span>首图规则</span>
              <select id="template-image-rule" v-model="draft.style.firstImageRule">
                <option value="cover">封面优先</option>
                <option value="optional">首图可选</option>
                <option value="none">不自动配图</option>
              </select>
            </label>
            <label class="te-field" for="template-tail">
              <span>尾注 <small class="te-counter">{{ draft.style.tailText.length }}/200</small></span>
              <textarea id="template-tail" v-model="draft.style.tailText" rows="2" maxlength="200" placeholder="可选：写在正文末尾的一句话" />
            </label>
          </div>
        </fieldset>

        <div class="te-form-footer">
          <div v-if="actionError" class="te-action-error" role="alert">
            <AlertCircle :size="15" aria-hidden="true" />
            <span id="name-error">{{ actionError }}</span>
            <button type="button" aria-label="关闭错误提示" @click="clearActionError"><X :size="14" /></button>
          </div>
          <p v-if="notice" class="te-notice" role="status"><Check :size="13" aria-hidden="true" /> {{ notice }}</p>

          <div v-if="deleteCandidate" class="te-delete-confirm" role="alertdialog" aria-modal="false" aria-labelledby="delete-title" aria-describedby="delete-description" @keydown.esc="cancelDelete">
            <strong id="delete-title">删除「{{ deleteCandidate.name }}」？</strong>
            <p id="delete-description">此操作无法撤销。若模板仍被任务或计划引用，请先清理引用。</p>
            <div>
              <button ref="deleteCancelButton" class="te-button secondary" type="button" :disabled="deleting" @click="cancelDelete">保留模板</button>
              <button class="te-button danger" type="button" :disabled="deleting" @click="confirmDelete">
                <LoaderCircle v-if="deleting" class="te-spin" :size="14" aria-hidden="true" />
                <Trash2 v-else :size="14" aria-hidden="true" />
                {{ deleting ? '正在删除' : '确认删除' }}
              </button>
            </div>
          </div>

          <div class="te-actions">
            <template v-if="isBuiltin">
              <button class="te-button primary" type="button" @click="copyPreset(currentPreset!)"><Copy :size="14" aria-hidden="true" /> 复制为自定义</button>
              <button class="te-button secondary" type="button" :disabled="!canApply" @click="applyTemplate"><ArrowUpRight :size="14" aria-hidden="true" /> 应用模板</button>
            </template>
            <template v-else>
              <button v-if="draft.id" class="te-button danger-quiet" type="button" :disabled="saving || deleting" @click="requestDelete"><Trash2 :size="14" aria-hidden="true" /> 删除</button>
              <button v-if="draft.id && isDirty" class="te-button secondary" type="button" :disabled="saving || deleting" @click="loadPreset(currentPreset!)">撤销更改</button>
              <button class="te-button secondary" type="button" :disabled="!canApply" :title="!canApply ? '保存模板后即可应用' : '应用此模板'" @click="applyTemplate"><ArrowUpRight :size="14" aria-hidden="true" /> 应用</button>
              <button class="te-button primary" type="submit" :disabled="saving || deleting">
                <LoaderCircle v-if="saving" class="te-spin" :size="14" aria-hidden="true" />
                <Save v-else :size="14" aria-hidden="true" />
                {{ saving ? '正在保存' : draft.id ? '保存更改' : '创建模板' }}
              </button>
            </template>
          </div>
          <p class="te-local-note"><HardDrive :size="12" aria-hidden="true" /> 模板仅保存在这台电脑</p>
        </div>
      </form>

      <section class="te-preview" aria-labelledby="preview-title" :aria-busy="previewLoading">
        <div class="te-preview-head">
          <div>
            <span class="te-section-no">03</span>
            <h3 id="preview-title">实时预览</h3>
          </div>
          <button class="te-icon-button" type="button" aria-label="刷新模板预览" title="刷新预览" :disabled="previewLoading" @click="refreshPreview">
            <RefreshCw :size="14" :class="{ 'te-spin': previewLoading }" aria-hidden="true" />
          </button>
        </div>
        <div class="te-preview-meta"><span class="te-live-dot" /> 固定样例 · 样式实时同步</div>

        <div class="te-preview-stage">
          <iframe v-if="previewDocument" :srcdoc="previewDocument" sandbox="" title="模板排版效果预览" />
          <div v-if="!previewDocument && !previewError" class="te-preview-placeholder">
            <LayoutTemplate :size="28" aria-hidden="true" />
            <p>正在排第一篇样例…</p>
          </div>
          <div v-if="previewLoading" class="te-preview-loading" role="status"><LoaderCircle class="te-spin" :size="16" aria-hidden="true" /> 正在更新预览</div>
          <div v-if="previewError" class="te-preview-error" role="alert">
            <AlertCircle :size="18" aria-hidden="true" />
            <p>{{ previewError }}</p>
            <button class="te-button secondary small" type="button" @click="refreshPreview">重新预览</button>
          </div>
        </div>

        <footer class="te-preview-footer">
          <span v-if="previewStats">{{ previewStats.characters }} 字 · 约 {{ previewStats.readingMinutes }} 分钟</span>
          <span v-else>样例预览</span>
          <span>首图规则随预览同步</span>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.template-editor {
  --te-ink: var(--ink, #292923);
  --te-muted: var(--muted, #827b6e);
  --te-paper: var(--paper, #eee9df);
  --te-paper-light: var(--paper-light, #f8f5ee);
  --te-line: var(--line, #d7cfc1);
  --te-red: var(--red, #a44732);
  container-type: inline-size;
  min-width: 0;
  max-width: 100%;
  color: var(--te-ink);
}

.te-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
  padding-bottom: 23px;
  border-bottom: 1px solid var(--te-line);
}

.te-eyebrow {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--te-red);
  font-family: Georgia, serif;
  font-size: 9px;
  letter-spacing: 2.2px;
}

.te-eyebrow span { width: 24px; height: 1px; background: #a447326b; }
.te-heading h2 {
  margin: 12px 0 8px;
  font-family: 'Noto Serif SC', 'Songti SC', 'STSong', serif;
  font-size: clamp(27px, 2.4vw, 38px);
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -.05em;
}
.te-heading p { margin: 0; color: var(--te-muted); font-size: 11px; line-height: 1.8; }

.te-layout {
  display: grid;
  grid-template-columns: minmax(215px, .7fr) minmax(345px, 1fr) minmax(370px, 1.15fr);
  grid-template-areas: 'library form preview';
  gap: 18px;
  align-items: start;
}

.te-library, .te-form, .te-preview {
  min-width: 0;
  border: 1px solid var(--te-line);
  background: var(--te-paper-light);
}
.te-library { grid-area: library; position: sticky; top: 18px; }
.te-form { grid-area: form; }
.te-preview { grid-area: preview; position: sticky; top: 18px; overflow: hidden; background: #e8e1d5; }

.te-library-head, .te-form-head, .te-preview-head {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 18px;
  border-bottom: 1px solid var(--te-line);
  background: #f4f0e7;
}
.te-library-head > div, .te-form-head > div, .te-preview-head > div { display: flex; align-items: center; gap: 9px; }
.te-library-head h3, .te-form-head h3, .te-preview-head h3 { margin: 0; font-size: 12px; font-weight: 600; }
.te-section-no {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid #cfc6b7;
  color: #8b8172;
  font-family: Georgia, serif;
  font-size: 9px;
}
.te-count { color: #93897a; font-family: Georgia, serif; font-size: 10px; }
.te-group-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 17px 16px 8px;
  color: #8c8172;
  font-size: 9px;
  letter-spacing: 1px;
}
.te-group-label small { font-family: Georgia, serif; font-size: 9px; }
.te-list { display: flex; flex-direction: column; }
.te-list-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 11px;
  width: 100%;
  min-width: 0;
  padding: 14px 15px;
  border: 0;
  border-bottom: 1px solid #e0d8cb;
  background: transparent;
  text-align: left;
  transition: background .18s ease, box-shadow .18s ease;
}
.te-list-item:hover { background: #eee8dd80; }
.te-list-item.active { background: #a4473209; box-shadow: inset 2px 0 var(--te-red); }
.te-glyph {
  display: grid;
  place-items: center;
  width: 34px;
  height: 39px;
  border: 1px solid #d7cfc1;
  background: #fffdf7;
  font-size: 15px;
}
.te-item-copy { display: block; min-width: 0; }
.te-item-title { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; overflow-wrap: anywhere; }
.te-item-title svg { flex: 0 0 auto; color: #9b9080; }
.te-item-description {
  display: -webkit-box;
  overflow: hidden;
  margin: 6px 0;
  color: #8e8374;
  font-size: 9px;
  line-height: 1.7;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.te-item-copy small { color: #a09483; font-size: 8px; }
.te-library-note { display: flex; align-items: flex-start; gap: 6px; margin: 0; padding: 15px; color: #968b7c; font-size: 8px; line-height: 1.7; }
.te-library-note svg { flex: 0 0 auto; margin-top: 1px; }
.te-library-empty { display: grid; place-items: center; gap: 12px; padding: 40px 20px; color: #a09482; text-align: center; }
.te-library-empty p { margin: 0; font-size: 10px; line-height: 1.9; }

.te-mode { display: inline-flex; align-items: center; gap: 5px; padding: 4px 7px; border: 1px solid #d6cebf; color: #8b8171; font-size: 8px; white-space: nowrap; }
.te-mode.readonly { color: #8d6756; border-color: #d9c4b7; background: #a4473207; }
.te-mode-dot { width: 4px; height: 4px; border-radius: 50%; background: #718468; }
.te-readonly-note { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 5px 8px; margin: 17px 20px 0; padding: 12px; border-left: 2px solid #b07a61; background: #efe7db; color: #806c5b; }
.te-readonly-note > svg { margin-top: 2px; }
.te-readonly-note p { margin: 0; font-size: 9px; line-height: 1.8; }
.te-inline-button { grid-column: 2; display: inline-flex; align-items: center; gap: 5px; justify-self: start; padding: 2px 0; border: 0; background: none; color: var(--te-red); font-size: 9px; }
.te-inline-button:hover { text-decoration: underline; text-underline-offset: 3px; }

.te-fields { min-width: 0; margin: 0; padding: 0; border: 0; }
.te-field-section { padding: 20px; border-bottom: 1px solid #dfd7ca; }
.te-field-section:last-child { border-bottom: 0; }
.te-field-section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 17px; }
.te-field-section-title span { font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 12px; font-weight: 600; }
.te-field-section-title small { color: #a19584; font-family: Georgia, serif; font-size: 7px; letter-spacing: 1.2px; }
.te-field { display: block; min-width: 0; margin-top: 14px; }
.te-field-section-title + .te-field { margin-top: 0; }
.te-field > span:first-child { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; color: #7d7263; font-size: 9px; }
.te-field b { color: var(--te-red); font-weight: 400; }
.te-field input[type='text'], .te-field textarea, .te-field select, .te-number-wrap {
  width: 100%;
  min-width: 0;
  border: 1px solid #d7cfc1;
  border-radius: 2px;
  background: #fffdf7;
  color: #4c463c;
  font-size: 11px;
  transition: border-color .18s ease, background .18s ease;
}
.te-field input[type='text'], .te-field select { height: 38px; padding: 0 10px; }
.te-field textarea { display: block; resize: vertical; min-height: 62px; padding: 9px 10px; line-height: 1.7; }
.te-field input::placeholder, .te-field textarea::placeholder { color: #b0a594; }
.te-field input:hover:not(:disabled), .te-field textarea:hover:not(:disabled), .te-field select:hover:not(:disabled), .te-number-wrap:hover { border-color: #b8ac99; }
.te-field input:focus-visible, .te-field textarea:focus-visible, .te-field select:focus-visible, .te-number-wrap:focus-within { outline: 2px solid #a4473266; outline-offset: 2px; border-color: var(--te-red); }
.te-field input[aria-invalid='true'] { border-color: var(--te-red); }
.te-field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.te-number-wrap { display: flex; align-items: center; height: 38px; overflow: hidden; }
.te-number-wrap input { width: 100%; min-width: 0; height: 100%; padding: 0 4px 0 10px; border: 0; outline: 0; background: transparent; color: #4c463c; font-size: 11px; }
.te-number-wrap small { flex: 0 0 auto; padding-right: 9px; color: #a19584; font-size: 8px; }
.te-counter { color: #a19584; font-family: Georgia, serif; font-size: 8px; }
.te-fields:disabled .te-field { opacity: .68; }
.te-fields:disabled input, .te-fields:disabled textarea, .te-fields:disabled select { cursor: not-allowed; background: #f1ece3; }

.te-accent-control { display: flex; align-items: center; gap: 10px; min-width: 0; }
.te-accent-control > input { flex: 0 0 auto; width: 38px; height: 34px; padding: 3px; border: 1px solid #d7cfc1; border-radius: 2px; background: #fffdf7; cursor: pointer; }
.te-accent-control output { color: #887c6c; font-family: Georgia, serif; font-size: 9px; }
.te-swatches { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.te-swatches button { display: grid; place-items: center; width: 21px; height: 21px; padding: 0; border: 2px solid var(--te-paper-light); border-radius: 50%; outline: 1px solid transparent; background: var(--swatch); color: #fffdf7; }
.te-swatches button[aria-pressed='true'] { outline-color: #8f8373; }
.te-swatches button:focus-visible { outline: 2px solid var(--te-red); outline-offset: 2px; }

.te-form-footer { padding: 16px 20px; border-top: 1px solid var(--te-line); background: #f4f0e7; }
.te-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.te-button {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 9px 13px;
  border: 1px solid transparent;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 500;
  line-height: 1.2;
  transition: background .18s ease, border-color .18s ease, color .18s ease;
}
.te-button:not(:disabled):active { transform: translateY(1px); }
.te-button.primary { border-color: var(--te-red); background: var(--te-red); color: #fff9ef; }
.te-button.primary:hover:not(:disabled) { border-color: #853622; background: #853622; }
.te-button.secondary { border-color: #d4ccbd; background: #f8f4ec; color: #655c4f; }
.te-button.secondary:hover:not(:disabled) { border-color: #aaa08f; background: #fffaf1; }
.te-button.danger { border-color: var(--te-red); background: var(--te-red); color: #fff9ef; }
.te-button.danger:hover:not(:disabled) { background: #853622; }
.te-button.danger-quiet { margin-right: auto; padding-right: 4px; padding-left: 4px; background: transparent; color: #a15c44; }
.te-button.danger-quiet:hover:not(:disabled) { color: #813b29; text-decoration: underline; text-underline-offset: 3px; }
.te-button.small { min-height: 31px; padding: 6px 9px; font-size: 9px; }
.te-button:focus-visible, .te-icon-button:focus-visible, .te-inline-button:focus-visible, .te-swatches button:focus-visible { outline: 2px solid var(--te-red); outline-offset: 3px; }
.te-local-note { display: flex; align-items: center; justify-content: flex-end; gap: 5px; margin: 12px 0 0; color: #a09687; font-size: 8px; }
.te-action-error { display: flex; align-items: flex-start; gap: 7px; margin-bottom: 12px; padding: 9px 10px; border-left: 2px solid var(--te-red); background: #f1e3da; color: #8f4b36; font-size: 9px; line-height: 1.7; overflow-wrap: anywhere; }
.te-action-error > svg { flex: 0 0 auto; margin-top: 1px; }
.te-action-error span { flex: 1; min-width: 0; }
.te-action-error button { flex: 0 0 auto; display: grid; place-items: center; padding: 1px; border: 0; background: none; color: inherit; }
.te-notice { display: flex; align-items: center; gap: 5px; margin: 0 0 12px; color: #587050; font-size: 9px; line-height: 1.6; }
.te-delete-confirm { margin-bottom: 14px; padding: 13px; border: 1px solid #d8b9a9; background: #f5e9e0; }
.te-delete-confirm strong { color: #813f2d; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 12px; }
.te-delete-confirm p { margin: 7px 0 12px; color: #94705e; font-size: 9px; line-height: 1.7; }
.te-delete-confirm > div { display: flex; justify-content: flex-end; gap: 7px; }

.te-preview-meta { display: flex; align-items: center; gap: 6px; padding: 10px 17px; border-bottom: 1px solid #d6cdbf; color: #8b8171; font-size: 8px; }
.te-live-dot { width: 5px; height: 5px; border-radius: 50%; background: #78906a; }
.te-icon-button { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 0; border-radius: 2px; background: transparent; color: #8a8173; }
.te-icon-button:hover:not(:disabled) { background: #ddd6ca80; color: var(--te-ink); }
.te-preview-stage {
  position: relative;
  height: 664px;
  overflow: hidden;
  background-color: #e8e1d5;
  background-image: radial-gradient(#c8bfb075 .55px, transparent .55px);
  background-size: 5px 5px;
}
.te-preview-stage iframe { display: block; width: 100%; height: 100%; border: 0; background: #fffdf7; }
.te-preview-placeholder { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 13px; color: #a09482; }
.te-preview-placeholder p { margin: 0; font-size: 10px; }
.te-preview-loading { position: absolute; top: 12px; right: 12px; display: flex; align-items: center; gap: 6px; padding: 7px 9px; border: 1px solid #d6cdbf; background: #f6f1e8ed; color: #7f7363; font-size: 8px; }
.te-preview-error { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 30px; background: #f3ece2f5; color: #99573f; text-align: center; }
.te-preview-error p { max-width: 280px; margin: 0; font-size: 10px; line-height: 1.8; overflow-wrap: anywhere; }
.te-preview-footer { display: flex; justify-content: space-between; gap: 10px; padding: 11px 15px; border-top: 1px solid #d3cabc; background: #f1ece2; color: #958b7c; font-size: 8px; }
.te-spin { animation: te-spin .9s linear infinite; }
.te-visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
@keyframes te-spin { to { transform: rotate(360deg); } }

@container (max-width: 1220px) {
  .te-layout { grid-template-columns: minmax(220px, .62fr) minmax(345px, 1fr); grid-template-areas: 'library form' 'preview preview'; }
  .te-library, .te-preview { position: static; }
  .te-preview-stage { height: 620px; }
}

@container (max-width: 790px) {
  .te-layout { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'library' 'form' 'preview'; }
  .te-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); max-height: 330px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #c2b9aa transparent; }
  .te-list-item { border-right: 1px solid #e0d8cb; }
  .te-preview-stage { height: 600px; }
}

@container (max-width: 520px) {
  .te-heading { align-items: flex-start; flex-direction: column; gap: 17px; margin-bottom: 20px; padding-bottom: 19px; }
  .te-heading .te-button { width: 100%; }
  .te-list { grid-template-columns: minmax(0, 1fr); max-height: 300px; }
  .te-list-item { border-right: 0; }
  .te-library-head, .te-form-head, .te-preview-head { padding: 0 15px; }
  .te-field-section { padding: 17px 15px; }
  .te-form-footer { padding: 15px; }
  .te-actions .te-button { flex: 1 1 125px; }
  .te-actions .te-button.danger-quiet { flex-basis: auto; margin-right: auto; }
  .te-accent-control { flex-wrap: wrap; }
  .te-swatches { margin-left: 0; }
  .te-preview-stage { height: 550px; }
  .te-preview-footer { flex-direction: column; gap: 4px; }
  .te-readonly-note { margin-right: 15px; margin-left: 15px; }
}

@media (prefers-reduced-motion: reduce) {
  .te-list-item, .te-field input, .te-field textarea, .te-field select, .te-number-wrap, .te-button { transition: none; }
  .te-spin { animation-duration: 1.8s; }
}
</style>
