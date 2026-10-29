import { useEffect, useState, type ReactNode } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { ArrowLeft, CircleHelp, Clock, GitCompare, HardDrive, RefreshCw, ScrollText } from "lucide-react"
import { toast } from "sonner"
import { api, formatBytes, formatTime } from "../lib/api.ts"
import { cn } from "../lib/utils.ts"
import { diffLabels, platformLabels, syncLabels, triggerLabels, type Repo, type Settings, type SyncLog } from "../lib/types.ts"
import { RepoBrowser } from "../components/repo-browser.tsx"
import { RepoForm } from "../components/repo-form.tsx"
import { StatusPill } from "../components/status-pill.tsx"
import { Badge, Card } from "../components/ui/card.tsx"
import { Button } from "../components/ui/button.tsx"
import { Modal } from "../components/ui/modal.tsx"

type Commit = { sha: string; author: string; authored_at: string; subject: string }

export function RepoDetailPage() {
  const params = useParams()
  const navigate = useNavigate()
  const id = params.id
  const [repo, setRepo] = useState<Repo | null>(null)
  const [commits, setCommits] = useState<Commit[]>([])
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [addingStorage, setAddingStorage] = useState(false)
  const [section, setSection] = useState<"content" | "storage" | "logs" | "commits">("content")
  const [busy, setBusy] = useState("")

  const load = async () => {
    if (!id) return
    const [data, commitData, logData] = await Promise.all([
      api<Repo>(`/api/repos/${id}`),
      api<{ items: Commit[] }>(`/api/repos/${id}/commits`),
      api<{ items: SyncLog[] }>(`/api/logs?repo_id=${id}&limit=50`),
    ])
    setRepo(data)
    setCommits(commitData.items)
    setLogs(logData.items)
  }

  useEffect(() => {
    void load().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "加载失败"))
  }, [id])

  const run = async (action: "sync" | "diff" | "summary") => {
    if (!id) return
    setBusy(action)
    try {
      if (action === "summary") {
        const data = await api<Repo>(`/api/repos/${id}/summary`, { method: "POST" })
        setRepo(data)
        toast.success(data.summary.trim() ? "概要已生成" : "AI未生成")
      } else {
        const data = await api<{ repo: Repo; diff_status?: string; upstream_error?: string }>(`/api/repos/${id}/${action}`, { method: "POST" })
        setRepo(data.repo)
        toast.success(action === "diff" ? `差异结果：${diffLabels[data.diff_status ?? data.repo.diff_status] ?? data.repo.diff_status}` : "同步已完成")
        if (data.upstream_error) toast.error(data.upstream_error)
        await load()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "操作失败")
    } finally {
      setBusy("")
    }
  }

  const retryStorage = async (targetId: number) => {
    if (!id) return
    setBusy(`retry-${targetId}`)
    try {
      const data = await api<{ repo: Repo; status: string }>(`/api/repos/${id}/targets/${targetId}/retry`, { method: "POST" })
      const place = data.repo.storages.find((item) => item.id === targetId)
      if (data.status === "success") toast.success("这一处保存方式已重试成功")
      else toast.error(place?.last_error || "重试失败")
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "重试失败")
    } finally {
      setBusy("")
    }
  }

  const remove = async () => {
    if (!id) return
    const data = await api<{ warnings: string[] }>(`/api/repos/${id}`, { method: "DELETE" })
    if (data.warnings.length) toast.error(data.warnings.join("；"))
    navigate("/")
  }

  if (!repo) return <p className="text-sm text-muted-foreground">正在加载仓库…</p>

  return (
    <div className="space-y-6">
      <div>
        <Link className="inline-flex min-h-11 items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" to="/">
          <ArrowLeft className="size-4" aria-hidden="true" />
          返回列表
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{repo.name}</h1>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{repo.upstream_url}</p>
          </div>
          <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={Boolean(busy)} onClick={() => void run("diff")}>{busy === "diff" ? "检测中…" : "检测差异"}</Button>
          <Button disabled={Boolean(busy)} onClick={() => void run("sync")}>{busy === "sync" ? "同步中…" : "立即同步"}</Button>
          <Button variant="outline" onClick={() => setEditing(true)}>编辑</Button>
          <Button variant="destructive" onClick={() => setConfirmDelete(true)}>删除</Button>
          </div>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={RefreshCw} label="同步" value={<StatusPill status={repo.sync_status} labels={syncLabels} />} hint={formatTime(repo.last_sync_at)} />
        <Stat icon={GitCompare} label="差异" value={<StatusPill status={repo.diff_status} labels={diffLabels} />} hint={formatTime(repo.last_diff_at)} />
        <Stat icon={Clock} label="下次执行" value={repo.schedule.paused ? "已暂停" : formatTime(repo.next_run_at)} />
        <Stat icon={HardDrive} label="体积" value={formatBytes(repo.size_bytes)} hint={`${repo.branch_count} 分支 · ${repo.tag_count} 标签`} />
      </div>
      <Card className="space-y-3 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">概要</h2>
          <Button variant="outline" disabled={busy === "summary"} onClick={() => void run("summary")}>{busy === "summary" ? "生成中…" : repo.summary.trim() ? "重新生成" : "生成概要"}</Button>
        </div>
        <p className={repo.summary.trim() ? "whitespace-pre-wrap text-sm leading-6" : "text-sm leading-6 text-muted-foreground"}>{repo.summary.trim() || "AI未生成"}</p>
      </Card>
      <div role="tablist" aria-label="仓库详情" className="flex gap-1 overflow-x-auto border-b">
        {([
          ["content", "内容"],
          ["storage", "保存方式"],
          ["logs", "日志"],
          ["commits", "提交"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={section === value}
            className={cn("min-h-11 shrink-0 cursor-pointer border-b-2 px-3 text-sm", section === value ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}
            onClick={() => setSection(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {section === "content" && id ? <RepoBrowser key={repo.last_sync_at ?? "none"} repoId={Number(id)} branch={repo.default_branch} upstreamUrl={repo.upstream_url} platform={repo.platform} /> : null}
      {section === "storage" ? <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">保存方式</h2>
          <Button variant="outline" onClick={() => setAddingStorage(true)}>添加保存方式</Button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">默认分支 {repo.default_branch || "—"} · 上游 {platformLabels[repo.platform] ?? repo.platform}{repo.use_proxy ? " · 通过设置中的代理访问" : ""}</p>
        <ul className="mt-4 space-y-2 text-sm">
          {repo.storages.map((item) => (
            <li key={`${item.type}-${item.location}`} className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
              <Badge>{platformLabels[item.type] ?? item.type}</Badge>
              <span className="min-w-0 break-all font-mono text-xs">{item.location}</span>
              {item.type !== "local" ? <StatusPill status={item.last_status || "never"} labels={syncLabels} /> : null}
              {item.last_status === "failed" && item.id ? (
                <Button variant="outline" disabled={Boolean(busy)} onClick={() => void retryStorage(item.id!)}>{busy === `retry-${item.id}` ? "重试中…" : "重试"}</Button>
              ) : null}
              {item.last_error ? <span className="basis-full text-destructive">{item.last_error}</span> : null}
            </li>
          ))}
        </ul>
      </Card> : null}
      {section === "logs" ? <Card className="p-5">
        <div className="flex items-center gap-2">
          <ScrollText className="size-4 text-muted-foreground" aria-hidden="true" />
          <h2 className="font-semibold">同步日志</h2>
        </div>
        {logs.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">还没有这条仓库的同步记录。</p> : (
          <ul className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto">
            {logs.map((item) => (
              <li key={item.id} className="rounded-lg border bg-muted/30 px-3 py-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill status={item.status} labels={syncLabels} />
                    <span className="text-muted-foreground">{triggerLabels[item.trigger] ?? item.trigger}</span>
                  </div>
                  <p className="tabular-nums text-xs text-muted-foreground">{formatTime(item.started_at)} → {formatTime(item.finished_at)}</p>
                </div>
                <p className="mt-2">上游：{syncLabels[item.upstream_status] ?? item.upstream_status}{item.upstream_error ? `（${item.upstream_error}）` : ""}</p>
                {item.targets.length > 0 ? (
                  <ul className="mt-1 space-y-1 text-muted-foreground">
                    {item.targets.map((target) => (
                      <li key={`${item.id}-${target.target_type}-${target.name}`}>
                        {platformLabels[target.target_type] ?? target.target_type} {target.name}：{syncLabels[target.status] ?? target.status}
                        {target.error ? `（${target.error}）` : ""}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card> : null}
      {section === "commits" ? <Card className="p-5">
        <h2 className="font-semibold">最近提交</h2>
        <ul className="mt-3 max-h-[32rem] space-y-0 overflow-y-auto">
          {commits.map((commit) => (
            <li key={commit.sha} className="border-l-2 border-border py-3 pl-4">
              <p className="text-sm">{commit.subject}</p>
              <p className="mt-1 text-xs text-muted-foreground">{commit.author} · <span className="tabular-nums">{formatTime(commit.authored_at)}</span> · <span className="font-mono">{commit.sha.slice(0, 8)}</span></p>
            </li>
          ))}
        </ul>
      </Card> : null}
      {editing ? <RepoForm key={repo.id} open repo={repo} onClose={() => setEditing(false)} onSaved={() => void load()} /> : null}
      {addingStorage ? <AddStorageDialog repo={repo} onClose={() => setAddingStorage(false)} onSaved={() => { setSection("storage"); void load().then(() => run("sync")) }} /> : null}
      <Modal open={confirmDelete} title="删除仓库" onClose={() => setConfirmDelete(false)}>
        <p className="text-sm leading-6">将删除本系统记录，以及这个仓库在每种保存方式里的内容：本地镜像、WebDAV 目录，还有 GitHub 或 Gitee 上的目标仓库。如果保存目标和上游是同一个地址，上游会保留。同步进行中时不能删除。</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setConfirmDelete(false)}>取消</Button>
          <Button variant="destructive" onClick={() => void remove()}>确认删除</Button>
        </div>
      </Modal>
    </div>
  )
}

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Clock; label: string; value: ReactNode; hint?: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </div>
      <div className="mt-2 text-sm font-medium">{value}</div>
      {hint ? <p className="mt-1 text-xs tabular-nums text-muted-foreground">{hint}</p> : null}
    </Card>
  )
}

const remoteTypes = ["github", "gitee", "webdav"] as const
type StorageKind = "local" | (typeof remoteTypes)[number]

const blockedReasons: Record<(typeof remoteTypes)[number], string> = {
  github: "GitHub 保存方式使用设置里的访问令牌作为账户。当前还没有保存令牌，所以不能添加。",
  gitee: "Gitee 保存方式使用设置里的私人令牌作为账户。当前还没有保存令牌，所以不能添加。",
  webdav: "WebDAV 保存方式使用设置里的地址和用户名作为账户。当前还没有配齐，所以不能添加。",
}

function destinationText(repo: Repo, kind: StorageKind) {
  if (kind === "local") return "本地：镜像会放到设置里的本地目录。"
  if (kind === "webdav") return `WebDAV：目录为 /${repo.owner}/${repo.repo_name}。`
  if (kind === repo.platform) {
    return `${platformLabels[kind]}：fork 上游到设置里的账户，仓库名为 ${repo.repo_name}。页面上会显示上游链接。`
  }
  return `${platformLabels[kind]}：保存到设置里的账户下，仓库名为 ${repo.repo_name}。账户下还没有这个仓库时，同步会先创建一个私有空仓库。`
}

function AddStorageDialog({ repo, onClose, onSaved }: { repo: Repo; onClose: () => void; onSaved: () => void }) {
  const used = new Set(repo.targets.map((item) => item.target_type))
  const [picked, setPicked] = useState<StorageKind[]>([])
  const [pending, setPending] = useState(false)
  const [accounts, setAccounts] = useState({ ready: false, github: false, gitee: false, webdav: false })
  const [blocked, setBlocked] = useState<(typeof remoteTypes)[number] | "">("")

  useEffect(() => {
    void api<Settings>("/api/settings")
      .then((settings) => {
        setAccounts({
          ready: true,
          github: settings.github_token_set,
          gitee: settings.gitee_token_set,
          webdav: Boolean(settings.webdav_url.trim() && settings.webdav_username.trim()),
        })
      })
      .catch((error: unknown) => toast.error(error instanceof Error ? error.message : "无法读取平台账户"))
  }, [])

  const configured = (type: (typeof remoteTypes)[number]) => accounts[type]
  const toggle = (kind: StorageKind, checked: boolean) => {
    setPicked((current) => checked ? [...current, kind] : current.filter((item) => item !== kind))
  }

  const save = async () => {
    if (picked.length === 0) return
    setPending(true)
    try {
      const remotes = picked.filter((kind) => kind !== "local")
      const targets = [
        ...repo.targets.map((item) => ({ target_type: item.target_type, remote_url: item.remote_url })),
        ...remotes.map((kind) => ({ target_type: kind, remote_url: "" })),
      ]
      await api(`/api/repos/${repo.id}`, {
        method: "PATCH",
        body: JSON.stringify({ save_local: repo.save_local || picked.includes("local"), targets: remotes.length > 0 ? targets : undefined }),
      })
      toast.success("保存方式已添加，开始首次同步")
      onClose()
      onSaved()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "添加失败")
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal open title="添加保存方式" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm leading-6 text-muted-foreground">可以同时选择多种。已使用的不能再选。GitHub、Gitee 和 WebDAV 使用设置里的账户，位置按这个仓库自动确定。添加后会立刻做一次同步。</p>
        <div className="space-y-1">
          <label className={cn("flex min-h-11 items-center gap-2 text-sm", repo.save_local && "text-muted-foreground")}>
            <input type="checkbox" checked={repo.save_local || picked.includes("local")} disabled={repo.save_local} onChange={(event) => toggle("local", event.target.checked)} />
            本地{repo.save_local ? "（已使用）" : ""}
          </label>
          {remoteTypes.map((type) => {
            const taken = used.has(type)
            const ready = accounts.ready && configured(type)
            return (
              <div key={type} className="flex min-h-11 items-center gap-1 text-sm">
                <label className={cn("flex items-center gap-2", ready || taken ? "" : "text-muted-foreground")}>
                  <input
                    type="checkbox"
                    checked={taken || picked.includes(type)}
                    disabled={!accounts.ready || taken || !ready}
                    onChange={(event) => {
                      if (!ready || taken) return
                      toggle(type, event.target.checked)
                    }}
                  />
                  {platformLabels[type]}{taken ? "（已使用）" : ""}
                </label>
                {accounts.ready && !ready && !taken ? (
                  <Button type="button" variant="ghost" className="size-11 px-0 text-muted-foreground" aria-label={`查看无法添加${platformLabels[type]}的原因`} onClick={() => setBlocked(type)}>
                    <CircleHelp className="size-4" aria-hidden="true" />
                  </Button>
                ) : null}
              </div>
            )
          })}
        </div>
        {picked.length > 0 ? (
          <ul className="space-y-1 text-sm text-muted-foreground">
            {picked.map((kind) => <li key={kind}>{destinationText(repo, kind)}</li>)}
          </ul>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button disabled={pending || picked.length === 0} onClick={() => void save()}>{pending ? "添加中…" : "添加并同步"}</Button>
        </div>
      </div>
      <Modal open={Boolean(blocked)} title={blocked ? `无法添加 ${platformLabels[blocked]}` : "无法添加"} onClose={() => setBlocked("")}>
        <p className="text-sm leading-6">{blocked ? blockedReasons[blocked] : ""}</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setBlocked("")}>关闭</Button>
          <Button asChild>
            <Link to="/settings" onClick={onClose}>前往设置</Link>
          </Button>
        </div>
      </Modal>
    </Modal>
  )
}
