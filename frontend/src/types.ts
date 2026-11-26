export interface Draft {
  id?: number
  title: string
  body: string
  source: string
  tags: string[]
  cover_image: string | null
  content_type: 'article' | 'video'
  video_path: string | null
  video_duration: number | null
  video_width: number | null
  video_height: number | null
  video_partition: string | null
  video_collection: string | null
  status: string
  created_at?: string
  updated_at?: string
}

export interface Preset {
  id: string
  name: string
  description: string
  platform_hint: string
  is_builtin?: boolean
  updated_at?: string | null
  style: {
    fontFamily: string
    fontSize: number
    lineHeight: number
    paragraphSpacing: number
    accent: string
    headingStyle: string
    quoteStyle: string
    firstImageRule: string
    tailText: string
  }
}

export interface MediaAsset {
  id: number
  kind: 'image' | 'video'
  original_name: string
  mime_type: string
  size_bytes: number
  width: number | null
  height: number | null
  duration: number | null
  stored_path: string
  url: string
  sha256: string
  source: string
  tags: string[]
  created_at: string
}

export interface AssetCapabilities {
  image_generation_configured: boolean
  max_image_upload_mb: number
  image_extensions: string[]
}

export interface Finding {
  term: string
  type: 'prohibited' | 'advertising' | 'links'
  message: string
}

export interface Preview {
  html: string
  preset_name: string
  stats: { characters: number; readingMinutes: number }
  findings: Finding[]
}

export interface Account {
  id: number
  platform: string
  nickname: string
  login_valid: boolean
  created_at: string
  message?: string
}

export interface VideoMetadata {
  video_path: string
  duration: number
  width: number
  height: number
  size_bytes: number
  codec: string
}

export interface VideoConfig {
  ffmpeg_available: boolean
  max_upload_mb: number
  max_duration_seconds: number
  extensions: string[]
}

export interface PublishTask {
  id: number
  draft_id: number
  draft_title: string
  account_id: number
  platform: string
  content_type: 'article' | 'video'
  preset_id: string
  status: string
  result_url: string | null
  error_msg: string | null
  retry_count: number
  max_retries: number
  next_retry_at: string | null
  scheduled_at: string | null
  schedule_plan_id: number | null
  submission_uncertain: boolean
  created_at: string
  updated_at: string
  logs: { level: string; message: string; created_at: string }[]
}

export interface MetricSnapshot {
  id: number
  task_id: number
  platform: string
  draft_title: string
  metric_date: string
  source: 'manual' | 'platform_export' | 'official_api'
  views: number
  reads: number
  plays: number
  likes: number
  comments: number
  shares: number
  favorites: number
  note: string
  collected_at: string
}

export interface MetricSnapshotInput {
  task_id: number
  metric_date: string
  source: MetricSnapshot['source']
  views: number
  reads: number
  plays: number
  likes: number
  comments: number
  shares: number
  favorites: number
  note: string
}

export interface AnalyticsOverview {
  generated_at: string
  period_days: number
  summary: {
    total_tasks: number
    period_tasks: number
    success: number
    failed: number
    active: number
    skipped: number
    success_rate: number
  }
  status_counts: Record<string, number>
  content_types: Record<string, number>
  platforms: { platform: string; total: number; success: number; failed: number }[]
  trend: { date: string; total: number; success: number; failed: number }[]
  metrics: {
    views: number
    reads: number
    plays: number
    likes: number
    comments: number
    shares: number
    favorites: number
    reach: number
    engagement: number
    engagement_rate: number
    snapshots: number
  }
  recent_metrics: MetricSnapshot[]
  collection_notice: string
}

export interface AuditEvent {
  id: number
  created_at: string
  actor: string
  action: string
  entity_type: string
  entity_id: number | null
  outcome: 'success' | 'denied' | 'error'
  message: string
  request_id: string
  metadata: Record<string, unknown>
}

export interface SchedulePlan {
  id: number
  name: string
  draft_id: number
  draft_title: string
  content_type: 'article' | 'video'
  account_ids: number[]
  account_names: string[]
  preset_id: string
  cron_expr: string | null
  scheduled_at: string | null
  enabled: boolean
  authorized: boolean
  authorization_valid: boolean
  last_run_at: string | null
  next_run_at: string | null
  created_at: string
}
