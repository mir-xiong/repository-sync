import { useEffect, useState } from "react"
import { ScrollText } from "lucide-react"
import { api, formatTime } from "../lib/api.ts"
import { platformLabels, syncLabels, triggerLabels, type SyncLog } from "../lib/types.ts"
import { EmptyState } from "../components/empty-state.tsx"
import { PageHeader } from "../components/page-header.tsx"
import { StatusPill } from "../components/status-pill.tsx"
import { Card } from "../components/ui/card.tsx"
import { Select } from "../components/ui/select.tsx"

export function LogsPage() {
  const [items, setItems] = useState<SyncLog[]>([])
  const [status, setStatus] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    const params = new URLSearchParams()
    if (status) params.set("status", status)
    void api<{ items: SyncLog[] }>(`/api/logs?${params.toString()}`)
      .then((data) => {
        setItems(data.items)
        setError("")
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "加载失败"))
  }, [status])

  return (
    <div className="space-y-6">
      <PageHeader
        title="同步日志"
        description="每次拉取、推送和跳过都会留在这里。"
        action={
          <Select value={status} aria-label="日志状态" onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="skipped">跳过</option>
            <option value="running">进行中</option>
          </Select>
        }
      />
      {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
      {items.length === 0 ? <EmptyState icon={ScrollText} title="这段时间没有日志" description="添加仓库或手动同步之后，记录会出现在这里。" /> : null}
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id} className="overflow-hidden p-0">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-muted/40 px-4 py-3">
              <div>
                <p className="font-medium">{item.repo_name || "已删除的仓库"}</p>
                <p className="mt-0.5 font-mono text-xs text-muted-foreground">{item.upstream_url}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill status={item.status} labels={syncLabels} />
                <span className="text-xs text-muted-foreground">{triggerLabels[item.trigger] ?? item.trigger}</span>
              </div>
            </div>
            <div className="space-y-2 px-4 py-3 text-sm">
              <p className="tabular-nums text-muted-foreground">{formatTime(item.started_at)} → {formatTime(item.finished_at)}</p>
              <p>上游：{syncLabels[item.upstream_status] ?? item.upstream_status} {item.upstream_error}</p>
              {item.targets.length > 0 ? (
                <ul className="space-y-1">
                  {item.targets.map((target) => (
                    <li key={`${item.id}-${target.target_type}-${target.name}`} className="text-muted-foreground">
                      {platformLabels[target.target_type] ?? target.target_type} {target.name}：{syncLabels[target.status] ?? target.status}
                      {target.error ? `（${target.error}）` : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
