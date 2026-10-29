export type Schedule = {
  type: "daily" | "weekly" | "monthly" | "cron"
  time: string | null
  weekday: number | null
  monthday: number | null
  cron: string | null
  paused: boolean
}

export type RepoTarget = {
  id?: number
  target_type: "gitee" | "github" | "webdav"
  remote_url: string
  last_status?: string
  last_error?: string
}

export type StoragePlace = {
  id?: number
  type: "local" | "gitee" | "github" | "webdav"
  location: string
  last_status?: string
  last_error?: string
}

export type Repo = {
  id: number
  name: string
  upstream_url: string
  platform: string
  owner: string
  repo_name: string
  summary: string
  summary_excerpt: string
  summary_source: string
  default_branch: string
  sync_status: string
  last_sync_at: string | null
  next_run_at: string | null
  diff_status: string
  last_diff_at: string | null
  size_bytes: number
  branch_count: number
  tag_count: number
  schedule: Schedule
  save_local: boolean
  use_proxy: boolean
  storages: StoragePlace[]
  targets: RepoTarget[]
}

export type SyncLog = {
  id: number
  repo_id: number | null
  repo_name: string
  upstream_url: string
  trigger: string
  status: string
  started_at: string | null
  finished_at: string | null
  upstream_status: string
  upstream_error: string
  targets: Array<{ name: string; target_type: string; status: string; error: string }>
}

export type Settings = {
  log_retention_days: number
  sync_concurrency: number
  local_mirror_dir: string
  proxy_url: string
  gitee_token_set: boolean
  github_token_set: boolean
  webdav_url: string
  webdav_username: string
  webdav_password_set: boolean
}

export type Provider = {
  id: number
  name: string
  base_url: string
  model: string
  enabled: boolean
  use_proxy: boolean
  api_key_set: boolean
}

export const syncLabels: Record<string, string> = {
  never: "从未同步",
  running: "同步中",
  success: "成功",
  failed: "失败",
  skipped: "跳过",
}

export const diffLabels: Record<string, string> = {
  unknown: "未检测",
  same: "一致",
  behind: "落后于上游",
  diverged: "历史分叉",
  failed: "检测失败",
}

export const triggerLabels: Record<string, string> = {
  initial: "首次添加",
  schedule: "定时",
  manual: "手动",
  retry: "重试",
}

export const platformLabels: Record<string, string> = {
  github: "GitHub",
  gitee: "Gitee",
  webdav: "WebDAV",
  local: "本地",
  file: "本地",
}
