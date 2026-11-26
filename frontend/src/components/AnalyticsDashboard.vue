<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, BookOpenText, CheckCircle2,
  Eye, FileDown, LoaderCircle, Plus, RefreshCw, Send, ShieldCheck,
} from 'lucide-vue-next'
import { api } from '../api'
import type { AnalyticsOverview, MetricSnapshotInput, PublishTask } from '../types'

const emit = defineEmits<{ saved: [] }>()

const PERIODS = [7, 30, 90]
const METRIC_FIELDS: { key: keyof Pick<MetricSnapshotInput, 'views' | 'reads' | 'plays' | 'likes' | 'comments' | 'shares' | 'favorites'>; label: string }[] = [
  { key: 'views', label: '浏览量' },
  { key: 'reads', label: '阅读量' },
  { key: 'plays', label: '播放量' },
  { key: 'likes', label: '点赞' },
  { key: 'comments', label: '评论' },
  { key: 'shares', label: '分享' },
  { key: 'favorites', label: '收藏' },
]
const SOURCE_LABELS = { manual: '手工录入', platform_export: '平台官方导出', official_api: '授权 API' }

const overview = ref<AnalyticsOverview | null>(null)
const eligibleTasks = ref<PublishTask[]>([])
const period = ref(30)
const loading = ref(true)
const loadError = ref('')
const formOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const today = localDateValue()
let dashboardRequest = 0

function emptyForm(): MetricSnapshotInput {
  return {
    task_id: 0, metric_date: today, source: 'manual', views: 0, reads: 0, plays: 0,
    likes: 0, comments: 0, shares: 0, favorites: 0, note: '',
  }
}
const form = reactive<MetricSnapshotInput>(emptyForm())

function localDateValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function platformLabel(platform: string) {
  return ({ csdn: 'CSDN', zhihu: '知乎', bilibili: '哔哩哔哩' })[platform] || platform
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value)
}

function compactNumber(value: number) {
  if (value >= 10000) return `${(value / 10000).toFixed(value >= 100000 ? 0 : 1)}万`
  return formatNumber(value)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(`${value}T00:00:00`))
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

const trendMax = computed(() => Math.max(1, ...(overview.value?.trend.map((item) => item.total) ?? [])))
const tickIndexes = computed(() => {
  const count = overview.value?.trend.length ?? 0
  return [...new Set([0, Math.floor((count - 1) / 2), count - 1].filter((index) => index >= 0))]
})
const selectedTask = computed(() => eligibleTasks.value.find((task) => task.id === form.task_id))
const totalEngagement = computed(() => {
  const metrics = overview.value?.metrics
  return metrics ? metrics.likes + metrics.comments + metrics.shares + metrics.favorites : 0
})

async function loadDashboard() {
  const requestId = ++dashboardRequest
  loading.value = true
  loadError.value = ''
  try {
    const [data, tasks] = await Promise.all([
      api.analytics(period.value),
      api.tasks({ status: 'success', limit: 500 }),
    ])
    if (requestId !== dashboardRequest) return
    overview.value = data
    eligibleTasks.value = tasks
    if (form.task_id && !tasks.some((task) => task.id === form.task_id)) resetForm()
  } catch (error) {
    if (requestId === dashboardRequest) loadError.value = error instanceof Error ? error.message : '看板加载失败'
  } finally {
    if (requestId === dashboardRequest) loading.value = false
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  formError.value = ''
}

function openForm() {
  formOpen.value = true
  resetForm()
  if (eligibleTasks.value.length === 1) form.task_id = eligibleTasks.value[0].id
}

async function saveMetric() {
  formError.value = ''
  if (!form.task_id || !selectedTask.value) {
    formError.value = '请选择一条已成功发布的任务。'
    return
  }
  if (!form.metric_date || form.metric_date > today) {
    formError.value = '指标日期不能晚于今天。'
    return
  }
  if (METRIC_FIELDS.some(({ key }) => !Number.isInteger(form[key]) || form[key] < 0)) {
    formError.value = '所有指标必须为大于或等于 0 的整数。'
    return
  }
  saving.value = true
  try {
    await api.saveMetric({ ...form, note: form.note.trim() })
    emit('saved')
    resetForm()
    formOpen.value = false
    await loadDashboard()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '指标保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadDashboard)
</script>

<template>
  <div class="analytics-dashboard">
    <div class="dashboard-toolbar">
      <div class="period-switch" aria-label="统计周期">
        <span>统计周期</span>
        <button v-for="days in PERIODS" :key="days" :class="{ active: period === days }" :aria-pressed="period === days" @click="period = days; loadDashboard()">近 {{ days }} 天</button>
      </div>
      <button class="button secondary" :disabled="loading" @click="loadDashboard"><RefreshCw :size="15" :class="{ spin: loading }" />刷新数据</button>
    </div>

    <p v-if="loadError" class="dashboard-error" role="alert"><ArrowDownRight :size="16" />{{ loadError }}</p>
    <div v-if="loading && !overview" class="dashboard-loading"><LoaderCircle class="spin" :size="26" /><p>正在整理本机发布数据…</p></div>

    <template v-else-if="overview">
      <section class="kpi-grid" aria-label="发布核心指标">
        <article class="kpi-item">
          <div class="kpi-label"><span>周期发布任务</span><Send :size="16" /></div>
          <strong>{{ compactNumber(overview.summary.period_tasks) }}</strong>
          <p>累计 {{ overview.summary.total_tasks }} 个发布任务</p>
        </article>
        <article class="kpi-item">
          <div class="kpi-label"><span>发布成功率</span><CheckCircle2 :size="16" /></div>
          <strong>{{ overview.summary.success_rate }}<small>%</small></strong>
          <p>{{ overview.summary.success }} 次成功 · {{ overview.summary.failed }} 次失败</p>
        </article>
        <article class="kpi-item accent">
          <div class="kpi-label"><span>内容触达</span><Eye :size="16" /></div>
          <strong>{{ compactNumber(overview.metrics.reach) }}</strong>
          <p>浏览、阅读与播放合计</p>
        </article>
        <article class="kpi-item">
          <div class="kpi-label"><span>互动率</span><Activity :size="16" /></div>
          <strong>{{ overview.metrics.engagement_rate }}<small>%</small></strong>
          <p>{{ formatNumber(totalEngagement) }} 次点赞、评论、分享与收藏</p>
        </article>
      </section>

      <div class="dashboard-main-grid">
        <section class="dashboard-panel trend-panel">
          <div class="panel-heading">
            <div><span class="section-kicker">PUBLISHING RHYTHM</span><h2>发布节奏</h2></div>
            <div class="chart-legend"><span><i class="total"></i>全部任务</span><span><i class="success"></i>成功</span></div>
          </div>
          <div v-if="overview.summary.period_tasks" class="trend-chart" role="img" :aria-label="`近 ${period} 天共创建 ${overview.summary.period_tasks} 个发布任务`">
            <div class="chart-grid-lines"><i></i><i></i><i></i></div>
            <div v-for="item in overview.trend" :key="item.date" class="trend-column" :title="`${formatDate(item.date)}：全部 ${item.total}，成功 ${item.success}，失败 ${item.failed}`">
              <div class="trend-bars">
                <i class="total-bar" :style="{ height: `${Math.max(2, item.total / trendMax * 100)}%` }"></i>
                <i class="success-bar" :style="{ height: `${Math.max(item.success ? 2 : 0, item.success / trendMax * 100)}%` }"></i>
              </div>
              <span v-if="tickIndexes.includes(overview.trend.indexOf(item))">{{ formatDate(item.date) }}</span>
            </div>
          </div>
          <div v-else class="panel-empty"><BarChart3 :size="26" /><strong>这段时间还没有发布任务</strong><p>创建发布任务后，每天的节奏会在这里呈现。</p></div>
          <div class="trend-foot"><span>日峰值 <strong>{{ trendMax === 1 && !overview.trend.some((item) => item.total) ? 0 : trendMax }}</strong> 个任务</span><span>{{ overview.generated_at.slice(0, 10) }} 更新</span></div>
        </section>

        <section class="dashboard-panel platform-panel">
          <div class="panel-heading"><div><span class="section-kicker">PLATFORM MIX</span><h2>平台分布</h2></div><span class="count-badge">{{ overview.platforms.length }}</span></div>
          <div v-if="overview.platforms.length" class="platform-breakdown">
            <article v-for="item in overview.platforms" :key="item.platform">
              <div class="platform-line"><strong>{{ platformLabel(item.platform) }}</strong><span>{{ item.total }} 个任务</span></div>
              <div class="platform-track"><i :style="{ width: `${item.total / overview.platforms[0].total * 100}%` }"></i></div>
              <div class="platform-detail"><span><i class="success-dot"></i>成功 {{ item.success }}</span><span><i class="failed-dot"></i>失败 {{ item.failed }}</span></div>
            </article>
          </div>
          <div v-else class="panel-empty compact"><BarChart3 :size="24" /><strong>暂无平台分布</strong></div>
          <div class="content-mix"><span>内容构成</span><p><BookOpenText :size="14" />文章 {{ overview.content_types.article || 0 }}</p><p><Activity :size="14" />视频 {{ overview.content_types.video || 0 }}</p></div>
        </section>
      </div>

      <div class="metrics-grid">
        <section class="dashboard-panel metric-totals">
          <div class="panel-heading"><div><span class="section-kicker">CONTENT SIGNALS</span><h2>内容数据</h2></div><span class="snapshot-count">{{ overview.metrics.snapshots }} 份有效快照</span></div>
          <div class="metric-number-grid">
            <div v-for="field in METRIC_FIELDS" :key="field.key"><span>{{ field.label }}</span><strong>{{ compactNumber(overview.metrics[field.key]) }}</strong></div>
          </div>
          <div class="collection-notice"><ShieldCheck :size="18" /><p>{{ overview.collection_notice }}</p></div>
        </section>

        <section class="dashboard-panel recent-metrics">
          <div class="panel-heading"><div><span class="section-kicker">LATEST SNAPSHOTS</span><h2>最近回采</h2></div><button class="button primary small" @click="openForm"><Plus :size="14" />录入指标</button></div>
          <div v-if="overview.recent_metrics.length" class="snapshot-list">
            <article v-for="snapshot in overview.recent_metrics.slice(0, 5)" :key="snapshot.id">
              <div class="snapshot-title"><strong>{{ snapshot.draft_title || `任务 #${snapshot.task_id}` }}</strong><span>{{ platformLabel(snapshot.platform) }}</span></div>
              <div class="snapshot-values"><span>触达 <b>{{ compactNumber(snapshot.views + snapshot.reads + snapshot.plays) }}</b></span><span>互动 <b>{{ compactNumber(snapshot.likes + snapshot.comments + snapshot.shares + snapshot.favorites) }}</b></span></div>
              <p>{{ formatDate(snapshot.metric_date) }} · {{ SOURCE_LABELS[snapshot.source] }} · {{ formatTime(snapshot.collected_at) }}</p>
            </article>
          </div>
          <div v-else class="panel-empty"><FileDown :size="27" /><strong>还没有内容数据</strong><p>从平台官方后台复制数据，手工录入或整理官方导出文件后录入。</p><button class="text-button" @click="openForm">录入第一份指标 <ArrowUpRight :size="14" /></button></div>
        </section>
      </div>
    </template>

    <section v-if="formOpen" class="metric-form-panel" aria-labelledby="metric-form-title">
      <div class="panel-heading"><div><span class="section-kicker">COMPLIANT COLLECTION</span><h2 id="metric-form-title">录入平台指标</h2></div><button class="icon-button" aria-label="关闭指标录入" @click="formOpen = false">×</button></div>
      <p class="form-intro">选择已成功发布的任务，填写平台官方页面或导出文件中的数据。相同任务、日期与来源再次提交会覆盖旧值。</p>
      <form @submit.prevent="saveMetric">
        <div class="metric-form-row">
          <label class="form-label metric-task-field">发布任务<select v-model.number="form.task_id" required><option :value="0">请选择已发布任务</option><option v-for="task in eligibleTasks" :key="task.id" :value="task.id">#{{ task.id }} · {{ platformLabel(task.platform) }} · {{ task.draft_title }}</option></select><small v-if="selectedTask">{{ selectedTask.result_url ? '平台回执已记录' : '任务已标记为发布成功' }}</small></label>
          <label class="form-label">指标日期<input v-model="form.metric_date" type="date" :max="today" required /></label>
          <label class="form-label">数据来源<select v-model="form.source"><option value="manual">手工录入</option><option value="platform_export">平台官方导出</option><option value="official_api">授权 API</option></select></label>
        </div>
        <div class="metric-input-grid">
          <label v-for="field in METRIC_FIELDS" :key="field.key" class="form-label">{{ field.label }}<input v-model.number="form[field.key]" type="number" min="0" max="1000000000000" step="1" required /></label>
        </div>
        <label class="form-label">备注<textarea v-model="form.note" rows="2" maxlength="300" placeholder="可选，例如：来自 CSDN 创作中心 11 月 26 日数据" /></label>
        <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>
        <div class="form-actions"><button type="button" class="button secondary" @click="formOpen = false">取消</button><button class="button primary" :disabled="saving || !eligibleTasks.length"><LoaderCircle v-if="saving" class="spin" :size="15" /><CheckCircle2 v-else :size="15" />保存指标</button></div>
        <p v-if="!eligibleTasks.length" class="form-note">暂无可录入数据的成功任务，请先完成一次发布。</p>
      </form>
    </section>
  </div>
</template>

<style scoped>
.analytics-dashboard { display: flex; flex-direction: column; gap: 22px; }
.dashboard-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 2px; }
.period-switch { display: flex; align-items: center; gap: 4px; }
.period-switch > span { margin-right: 9px; color: var(--muted); font-size: 10px; letter-spacing: .5px; }
.period-switch button { border: 1px solid transparent; border-radius: 2px; padding: 8px 12px; background: transparent; color: #7f7769; font-size: 10px; }
.period-switch button:hover { background: #ffffff45; }
.period-switch button.active { border-color: #cdbfae; background: #f8f4eb; color: var(--red); }
.dashboard-error { display: flex; align-items: center; gap: 8px; margin: 0; padding: 12px 14px; border-left: 3px solid var(--red); background: #a447320c; color: var(--red); font-size: 11px; }
.dashboard-loading { min-height: 260px; display: grid; place-content: center; justify-items: center; gap: 12px; color: var(--muted); font-size: 12px; }
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.kpi-item { display: flex; flex-direction: column; min-width: 0; padding: 22px 25px 20px; border-right: 1px solid var(--line); }
.kpi-item:last-child { border: 0; }
.kpi-item.accent { background: #e7ded0; }
.kpi-label { display: flex; justify-content: space-between; align-items: center; gap: 8px; color: #827a6c; font-size: 10px; }
.kpi-label svg { color: #a69883; }
.kpi-item.accent .kpi-label svg { color: var(--red); }
.kpi-item > strong { margin: 15px 0 10px; font-family: 'Noto Serif SC', Georgia, serif; font-size: clamp(29px, 3vw, 41px); font-weight: 500; line-height: 1; letter-spacing: -.045em; color: #39362e; }
.kpi-item > strong small { margin-left: 3px; font-family: Georgia, serif; font-size: 17px; color: #8b8070; }
.kpi-item > p { margin: 0; color: #948a7b; font-size: 9px; line-height: 1.6; }
.dashboard-main-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(260px, .8fr); gap: 20px; }
.dashboard-panel { min-width: 0; border: 1px solid var(--line); background: #f7f3eb; }
.panel-heading { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 19px 21px 17px; border-bottom: 1px solid #dfd7c9; }
.section-kicker { display: block; margin-bottom: 6px; color: var(--red); font-family: Georgia, serif; font-size: 8px; letter-spacing: 1.8px; }
.panel-heading h2 { margin: 0; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 18px; font-weight: 600; color: #39362e; }
.count-badge { min-width: 22px; height: 22px; display: grid; place-items: center; border: 1px solid #cec4b4; border-radius: 50%; color: #8e8374; font-family: Georgia, serif; font-size: 10px; }
.chart-legend { display: flex; align-items: center; gap: 12px; color: #8a8173; font-size: 9px; }
.chart-legend span { display: flex; align-items: center; gap: 5px; }
.chart-legend i { width: 7px; height: 7px; display: inline-block; }
.chart-legend .total { background: #d7caba; }
.chart-legend .success { background: var(--red); }
.trend-chart { position: relative; height: 222px; display: flex; align-items: stretch; gap: 4px; margin: 26px 22px 0; padding: 0 0 27px; border-bottom: 1px solid #d4cab9; }
.chart-grid-lines { position: absolute; inset: 0 0 27px; display: flex; flex-direction: column; justify-content: space-between; pointer-events: none; }
.chart-grid-lines i { width: 100%; border-top: 1px dashed #dfd6c7; }
.trend-column { position: relative; z-index: 1; flex: 1; min-width: 2px; height: 100%; display: flex; justify-content: center; }
.trend-bars { width: min(100%, 14px); height: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 2px; }
.trend-bars i { width: 5px; min-height: 0; display: block; transition: height .3s ease-out; }
.total-bar { background: #d1c3af; }
.success-bar { background: var(--red); }
.trend-column > span { position: absolute; top: calc(100% + 9px); color: #9c9182; font-family: Georgia, serif; font-size: 8px; white-space: nowrap; }
.trend-foot { display: flex; justify-content: space-between; gap: 12px; padding: 13px 22px 16px; color: #948979; font-size: 9px; }
.trend-foot strong { color: #6f6659; font-family: Georgia, serif; font-size: 11px; font-weight: 500; }
.panel-empty { min-height: 220px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; padding: 24px; color: #a19480; text-align: center; }
.panel-empty.compact { min-height: 190px; }
.panel-empty strong { margin-top: 4px; color: #756b5c; font-size: 12px; font-weight: 500; }
.panel-empty p { max-width: 310px; margin: 0; color: #9d9281; font-size: 10px; line-height: 1.8; }
.platform-breakdown { display: flex; flex-direction: column; gap: 22px; padding: 22px 21px; }
.platform-line { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 9px; font-size: 10px; }
.platform-line strong { color: #544d41; font-weight: 600; }
.platform-line span { color: #9b8f7e; font-size: 9px; }
.platform-track { height: 4px; background: #e5dccd; }
.platform-track i { height: 100%; display: block; background: #9d8a6f; }
.platform-detail { display: flex; gap: 15px; margin-top: 8px; color: #948878; font-size: 8px; }
.platform-detail span { display: flex; align-items: center; gap: 4px; }
.platform-detail i { width: 4px; height: 4px; border-radius: 50%; }
.success-dot { background: var(--green); }
.failed-dot { background: var(--red); }
.content-mix { display: flex; align-items: center; gap: 17px; padding: 14px 21px; border-top: 1px solid #dfd7c9; color: #8d8272; font-size: 9px; }
.content-mix > span { margin-right: auto; }
.content-mix p { display: flex; align-items: center; gap: 5px; margin: 0; }
.metrics-grid { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 20px; }
.snapshot-count { color: #968b7b; font-size: 9px; }
.metric-number-grid { display: grid; grid-template-columns: repeat(4, 1fr); padding: 8px 21px 20px; }
.metric-number-grid > div { display: flex; flex-direction: column; gap: 9px; padding: 17px 10px 12px 0; border-bottom: 1px solid #e3dacc; }
.metric-number-grid span { color: #938777; font-size: 9px; }
.metric-number-grid strong { font-family: Georgia, 'Noto Serif SC', serif; font-size: 23px; font-weight: 500; color: #494237; }
.collection-notice { display: flex; align-items: flex-start; gap: 10px; margin: 0 21px 21px; padding: 12px 13px; background: #e9e3d7; color: #736b5d; }
.collection-notice svg { flex: 0 0 auto; margin-top: 1px; color: var(--green); }
.collection-notice p { margin: 0; font-size: 9px; line-height: 1.8; }
.snapshot-list { padding: 0 21px; }
.snapshot-list article { padding: 13px 0; border-bottom: 1px solid #e1d8ca; }
.snapshot-list article:last-child { border: 0; }
.snapshot-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.snapshot-title strong { overflow: hidden; color: #514a3f; font-size: 11px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.snapshot-title > span { flex: 0 0 auto; color: var(--red); font-family: Georgia, serif; font-size: 9px; }
.snapshot-values { display: flex; gap: 22px; margin-top: 7px; color: #998d7c; font-size: 9px; }
.snapshot-values b { margin-left: 4px; color: #6d6253; font-family: Georgia, serif; font-size: 12px; font-weight: 500; }
.snapshot-list article > p { margin: 7px 0 0; color: #a09483; font-size: 8px; }
.metric-form-panel { border: 1px solid #cdbda8; background: #f8f4ec; }
.metric-form-panel .icon-button { font-family: Georgia, serif; font-size: 23px; }
.form-intro { margin: 17px 21px; color: #8b8070; font-size: 10px; line-height: 1.8; }
.metric-form-panel form { padding: 0 21px 21px; }
.metric-form-row { display: grid; grid-template-columns: minmax(240px, 2fr) minmax(145px, .8fr) minmax(150px, .8fr); gap: 14px; }
.form-label { display: flex; flex-direction: column; gap: 7px; color: #746a5b; font-size: 10px; }
.form-label small { color: #9d9180; font-size: 8px; font-weight: 400; }
.form-label input, .form-label select, .form-label textarea { width: 100%; min-height: 37px; border: 1px solid #d3c8b7; border-radius: 2px; padding: 8px 10px; background: #fcf9f2; color: #4c453b; font-size: 11px; }
.form-label textarea { resize: vertical; line-height: 1.6; }
.metric-input-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin: 15px 0; }
.form-error { margin: 12px 0 0; color: var(--red); font-size: 10px; }
.form-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 15px; }
.form-note { color: #9b8d7a; font-size: 9px; }
@media (max-width: 1220px) {
  .kpi-item { padding-inline: 17px; }
  .metric-input-grid { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 900px) {
  .dashboard-toolbar { align-items: flex-start; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .kpi-item:nth-child(2) { border-right: 0; }
  .kpi-item:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
  .dashboard-main-grid, .metrics-grid { grid-template-columns: 1fr; }
  .metric-form-row { grid-template-columns: 1fr 1fr; }
  .metric-task-field { grid-column: 1 / -1; }
}
@media (max-width: 620px) {
  .analytics-dashboard { gap: 15px; }
  .dashboard-toolbar { flex-direction: column; }
  .dashboard-toolbar > .button { align-self: flex-end; min-height: 33px; padding: 7px 10px; }
  .period-switch { width: 100%; gap: 2px; }
  .period-switch > span { margin-right: auto; }
  .period-switch button { padding: 7px 8px; }
  .kpi-item { padding: 17px 14px; }
  .kpi-item > strong { margin-top: 13px; font-size: 30px; }
  .kpi-item > p { font-size: 8px; }
  .panel-heading { padding: 16px; }
  .panel-heading h2 { font-size: 17px; }
  .trend-chart { height: 190px; margin-inline: 16px; gap: 2px; }
  .trend-foot { padding-inline: 16px; }
  .chart-legend { gap: 7px; font-size: 8px; }
  .platform-breakdown { padding-inline: 16px; }
  .content-mix { flex-wrap: wrap; padding-inline: 16px; }
  .metric-number-grid { grid-template-columns: repeat(3, 1fr); padding-inline: 16px; }
  .metric-number-grid strong { font-size: 21px; }
  .collection-notice { margin-inline: 16px; }
  .snapshot-list { padding-inline: 16px; }
  .metric-form-row { grid-template-columns: 1fr; }
  .metric-task-field { grid-column: auto; }
  .metric-input-grid { grid-template-columns: repeat(2, 1fr); }
  .metric-form-panel form, .form-intro { padding-inline: 16px; }
  .form-intro { margin-inline: 16px; }
  .snapshot-count { font-size: 8px; }
}
</style>
