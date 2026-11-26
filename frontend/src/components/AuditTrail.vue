<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, ChevronRight, CircleSlash, Filter, LoaderCircle, RefreshCw, ScrollText, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api'
import type { AuditEvent } from '../types'

const OUTCOME_LABELS: Record<AuditEvent['outcome'], string> = { success: '成功', denied: '已拦截', error: '异常' }
const ENTITY_LABELS: Record<string, string> = {
  draft: '草稿', account: '账号', task: '发布任务', publish_task: '发布任务', schedule: '调度计划', preset: '模板',
  asset: '素材', media: '媒体', metric: '平台指标', publish: '发布操作', api: '接口',
}
const ACTION_LABELS: Record<string, string> = {
  'api.mutation': '接口操作', 'task.compliance_blocked': '合规拦截', 'task.compliance_passed': '合规通过',
  'task.preparation_failed': '发布准备失败', 'task.published': '平台发布回执', 'task.publish_failed': '平台发布失败',
  'task.recovered': '任务恢复', 'task.paused': '任务暂停', 'task.resumed': '任务恢复', 'task.skipped': '任务跳过',
}

const events = ref<AuditEvent[]>([])
const outcome = ref<AuditEvent['outcome'] | 'all'>('all')
const entityType = ref('all')
const loading = ref(true)
const loadError = ref('')
const expandedId = ref<number | null>(null)
const entityTypes = ['all', 'draft', 'account', 'publish_task', 'schedule', 'preset', 'asset', 'media', 'metric', 'publish']

const summary = computed(() => ({
  success: events.value.filter((event) => event.outcome === 'success').length,
  denied: events.value.filter((event) => event.outcome === 'denied').length,
  error: events.value.filter((event) => event.outcome === 'error').length,
}))

async function loadEvents() {
  loading.value = true
  loadError.value = ''
  try {
    events.value = await api.auditEvents({
      outcome: outcome.value === 'all' ? undefined : outcome.value,
      entityType: entityType.value === 'all' ? undefined : entityType.value,
    })
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '审计日志加载失败'
  } finally {
    loading.value = false
  }
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).format(new Date(value))
}

function metadata(event: AuditEvent): Record<string, unknown> | null {
  return event.metadata && typeof event.metadata === 'object' ? event.metadata : null
}

function entityLabel(event: AuditEvent) {
  const type = ENTITY_LABELS[event.entity_type] || event.entity_type
  return event.entity_id === null ? type : `${type} #${event.entity_id}`
}

onMounted(loadEvents)
</script>

<template>
  <section class="audit-trail" aria-labelledby="audit-title">
    <div class="audit-heading">
      <div><span class="section-kicker">LOCAL AUDIT TRAIL</span><h2 id="audit-title">全量操作审计</h2><p>记录本机接口操作与队列状态变化，正文、Cookie、凭证和请求头不会入库。</p></div>
      <button class="button secondary small" :disabled="loading" @click="loadEvents"><RefreshCw :size="14" :class="{ spin: loading }" />刷新审计</button>
    </div>
    <div class="audit-summary"><span><CheckCircle2 :size="14" />成功 {{ summary.success }}</span><span><CircleSlash :size="14" />拦截 {{ summary.denied }}</span><span><AlertTriangle :size="14" />异常 {{ summary.error }}</span><small>当前筛选最近 100 条</small></div>
    <div class="audit-filters">
      <Filter :size="14" />
      <div class="outcome-filters" aria-label="审计结果筛选">
        <button v-for="item in (['all', 'success', 'denied', 'error'] as const)" :key="item" :class="{ active: outcome === item }" :aria-pressed="outcome === item" @click="outcome = item; loadEvents()">{{ item === 'all' ? '全部结果' : OUTCOME_LABELS[item] }}</button>
      </div>
      <select v-model="entityType" aria-label="审计对象筛选" @change="loadEvents"><option v-for="type in entityTypes" :key="type" :value="type">{{ type === 'all' ? '全部对象' : ENTITY_LABELS[type] || type }}</option></select>
    </div>
    <p v-if="loadError" class="audit-error" role="alert">{{ loadError }}</p>
    <div v-if="loading && !events.length" class="audit-empty"><LoaderCircle class="spin" :size="24" /><p>正在读取审计日志…</p></div>
    <div v-else-if="!events.length" class="audit-empty"><ScrollText :size="28" /><strong>没有符合条件的审计记录</strong><p>新增、修改、发布和队列操作会自动留下轨迹。</p></div>
    <div v-else class="audit-list">
      <article v-for="event in events" :key="event.id" class="audit-row" :class="{ expanded: expandedId === event.id }">
        <button class="audit-row-main" :aria-expanded="expandedId === event.id" @click="expandedId = expandedId === event.id ? null : event.id">
          <span class="audit-outcome" :class="event.outcome"><CheckCircle2 v-if="event.outcome === 'success'" :size="17" /><CircleSlash v-else-if="event.outcome === 'denied'" :size="17" /><AlertTriangle v-else :size="17" /></span>
          <span class="audit-copy"><span class="audit-title"><strong>{{ event.message }}</strong><i :class="event.outcome">{{ OUTCOME_LABELS[event.outcome] }}</i></span><span class="audit-meta">{{ ACTION_LABELS[event.action] || event.action }} · {{ entityLabel(event) }} · {{ event.actor }} · {{ formatTime(event.created_at) }}</span></span>
          <ChevronRight :size="17" :class="{ rotated: expandedId === event.id }" />
        </button>
        <div v-if="expandedId === event.id" class="audit-detail">
          <div><span>请求标识</span><code>{{ event.request_id }}</code></div>
          <div><span>事件编号</span><code>#{{ event.id }}</code></div>
          <div><span>操作代码</span><code>{{ event.action }}</code></div>
          <div v-if="metadata(event)" class="audit-metadata"><span>安全元数据</span><pre>{{ JSON.stringify(metadata(event), null, 2) }}</pre></div>
        </div>
      </article>
    </div>
    <div class="audit-privacy"><ShieldCheck :size="16" /><p>审计记录仅保存在本地 SQLite 数据库中。系统会递归脱敏密钥字段，不记录请求正文、查询字符串、Authorization 或 Cookie。</p></div>
  </section>
</template>

<style scoped>
.audit-trail { margin-top: 38px; padding-top: 30px; border-top: 1px solid #c9bfae; }
.audit-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 22px; }
.section-kicker { display: block; margin-bottom: 6px; color: var(--red); font-family: Georgia, serif; font-size: 8px; letter-spacing: 1.8px; }
.audit-heading h2 { margin: 0 0 8px; font-family: 'Noto Serif SC', 'Songti SC', serif; font-size: 23px; font-weight: 600; color: #3b362e; }
.audit-heading p { margin: 0; color: #928675; font-size: 10px; line-height: 1.8; }
.audit-summary { display: flex; align-items: center; gap: 22px; margin-top: 19px; padding: 12px 15px; border: 1px solid var(--line); background: #f7f3eb; }
.audit-summary > span { display: flex; align-items: center; gap: 6px; color: #746b5d; font-size: 10px; }
.audit-summary > span:nth-child(1) svg { color: var(--green); }
.audit-summary > span:nth-child(2) svg { color: #a46e3e; }
.audit-summary > span:nth-child(3) svg { color: var(--red); }
.audit-summary small { margin-left: auto; color: #a09482; font-size: 8px; }
.audit-filters { display: flex; align-items: center; gap: 13px; margin-top: 13px; color: #948877; }
.outcome-filters { display: flex; gap: 3px; }
.outcome-filters button { border: 1px solid transparent; border-radius: 2px; padding: 7px 10px; background: transparent; color: #8b8070; font-size: 9px; }
.outcome-filters button.active { border-color: #d0c3b1; background: #f8f4ec; color: var(--red); }
.audit-filters select { min-height: 31px; margin-left: auto; border: 1px solid #d2c7b6; border-radius: 2px; padding: 5px 25px 5px 9px; background: #f6f1e8; color: #766c5d; font-size: 9px; }
.audit-error { color: var(--red); font-size: 10px; }
.audit-list { margin-top: 13px; border: 1px solid var(--line); background: #f7f3eb; }
.audit-row { border-bottom: 1px solid #e0d7c9; }
.audit-row:last-child { border: 0; }
.audit-row-main { width: 100%; display: flex; align-items: center; gap: 13px; border: 0; padding: 14px 16px; background: transparent; text-align: left; }
.audit-row-main:hover { background: #fbf8f1; }
.audit-outcome { width: 30px; height: 30px; flex: 0 0 auto; display: grid; place-items: center; border: 1px solid #d7cdbc; }
.audit-outcome.success { color: var(--green); background: #4f72580b; }
.audit-outcome.denied { color: #9b682e; background: #a46e3e0b; }
.audit-outcome.error { color: var(--red); background: #a447320a; }
.audit-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.audit-title { display: flex; align-items: center; gap: 9px; }
.audit-title strong { overflow: hidden; color: #554d41; font-size: 11px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.audit-title i { flex: 0 0 auto; padding: 2px 5px; border: 1px solid currentColor; font-size: 7px; font-style: normal; }
.audit-title i.success { color: var(--green); }
.audit-title i.denied { color: #9b682e; }
.audit-title i.error { color: var(--red); }
.audit-meta { overflow: hidden; color: #9d9080; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.audit-row-main > svg { flex: 0 0 auto; color: #a29480; transition: transform .2s; }
.rotated { transform: rotate(90deg); }
.audit-detail { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px 20px; padding: 14px 16px 17px 59px; border-top: 1px dashed #ddd3c3; background: #f1ece2; }
.audit-detail > div { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.audit-detail span { color: #9b8f7c; font-size: 8px; }
.audit-detail code, .audit-detail pre { margin: 0; color: #665d50; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 9px; white-space: pre-wrap; overflow-wrap: anywhere; }
.audit-metadata { grid-column: 1 / -1; }
.audit-metadata pre { padding: 10px 12px; border: 1px solid #dcd1c0; background: #f8f4ec; line-height: 1.6; }
.audit-empty { min-height: 170px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; margin-top: 13px; border: 1px solid var(--line); background: #f7f3eb; color: #9f927f; text-align: center; }
.audit-empty p { margin: 0; font-size: 9px; }
.audit-empty strong { color: #776c5d; font-size: 11px; font-weight: 500; }
.audit-privacy { display: flex; align-items: flex-start; gap: 9px; margin-top: 13px; color: #8b8070; }
.audit-privacy svg { flex: 0 0 auto; color: var(--green); }
.audit-privacy p { margin: 0; font-size: 9px; line-height: 1.8; }
@media (max-width: 900px) {
  .audit-detail { grid-template-columns: 1fr 1fr; padding-left: 16px; }
  .audit-metadata { grid-column: 1 / -1; }
}
@media (max-width: 620px) {
  .audit-trail { margin-top: 28px; padding-top: 24px; }
  .audit-heading { align-items: flex-start; }
  .audit-heading h2 { font-size: 21px; }
  .audit-heading p { font-size: 9px; }
  .audit-summary { gap: 13px; padding-inline: 11px; }
  .audit-summary small { display: none; }
  .audit-filters { flex-wrap: wrap; gap: 8px; }
  .audit-filters > svg { display: none; }
  .audit-filters select { min-height: 29px; }
  .outcome-filters { flex: 1; }
  .outcome-filters button { padding-inline: 8px; }
  .audit-row-main { gap: 9px; padding: 12px 10px; }
  .audit-outcome { width: 27px; height: 27px; }
  .audit-title { align-items: flex-start; }
  .audit-title strong { font-size: 10px; white-space: normal; }
  .audit-meta { font-size: 7px; }
  .audit-detail { grid-template-columns: 1fr; }
  .audit-metadata { grid-column: auto; }
}
</style>
