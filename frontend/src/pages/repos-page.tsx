import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Clock, CloudDownload, CloudUpload, FolderGit2, GitCompare, HardDrive, LayoutGrid, List, Plus } from "lucide-react"
import { toast } from "sonner"
import { api, formatTime } from "../lib/api.ts"
import { diffLabels, platformLabels, syncLabels, type Repo, type StoragePlace } from "../lib/types.ts"
import { EmptyState } from "../components/empty-state.tsx"
import { PageHeader } from "../components/page-header.tsx"
import { RepoForm } from "../components/repo-form.tsx"
import { StatusPill } from "../components/status-pill.tsx"
import { Badge, Card } from "../components/ui/card.tsx"
import { Button } from "../components/ui/button.tsx"
import { Input } from "../components/ui/input.tsx"
import { Modal } from "../components/ui/modal.tsx"
import { Select } from "../components/ui/select.tsx"

const VIEW_KEY = "repository-sync.view"
const DIFF_HINT = "比较本地镜像和上游的分支、标签。一致：两边相同。落后于上游：上游有本地没有的新提交。历史分叉：两边都有对方没有的提交。还没比较过是未检测。同步成功拉取上游后记为一致，拉取失败记为检测失败。"

export function ReposPage() {
  const [items, setItems] = useState<Repo[]>([])
  const [q, setQ] = useState("")
  const [platform, setPlatform] = useState("")
  const [syncStatus, setSyncStatus] = useState("")
  const [diffStatus, setDiffStatus] = useState("")
  const [sort, setSort] = useState("name")
  const [view, setView] = useState<"grid" | "list">(() => (localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid"))
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")
  const [ready, setReady] = useState(false)
  const [selected, setSelected] = useState<number[]>([])
  const [deleteIds, setDeleteIds] = useState<number[]>([])
  const [syncingIds, setSyncingIds] = useState<number[]>([])
  const [deleting, setDeleting] = useState(false)
  const syncingRef = useRef(new Set<number>())

  const load = async () => {
    const params = new URLSearchParams()
    if (q.trim()) params.set("q", q.trim())
    if (platform) params.set("platform", platform)
    if (syncStatus) params.set("sync_status", syncStatus)
    if (diffStatus) params.set("diff_status", diffStatus)
    params.set("sort", sort)
    params.set("order", sort === "last_sync" ? "desc" : "asc")
    try {
      const data = await api<{ items: Repo[] }>(`/api/repos?${params.toString()}`)
      setItems(data.items)
      setSelected((current) => current.filter((id) => data.items.some((item) => item.id === id)))
      setError("")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载失败")
    } finally {
      setReady(true)
    }
  }

  useEffect(() => {
    void load()
  }, [platform, syncStatus, diffStatus, sort])

  const changeView = (next: "grid" | "list") => {
    setView(next)
    localStorage.setItem(VIEW_KEY, next)
  }

  const toggle = (id: number, checked: boolean) => {
    setSelected((current) => checked ? [...current, id] : current.filter((item) => item !== id))
  }

  const toggleAll = (checked: boolean) => {
    setSelected(checked ? items.map((item) => item.id) : [])
  }

  const syncRepos = async (ids: number[]) => {
    const pending = ids.filter((id) => !syncingRef.current.has(id))
    if (!pending.length) return
    const names = new Map(items.map((item) => [item.id, item.name]))
    for (const id of pending) syncingRef.current.add(id)
    setSyncingIds([...syncingRef.current])
    const failures: string[] = []
    await Promise.all(pending.map(async (id) => {
      const name = names.get(id) ?? String(id)
      try {
        await api(`/api/repos/${id}/sync`, { method: "POST" })
      } catch (caught) {
        failures.push(`${name}：${caught instanceof Error ? caught.message : "同步失败"}`)
      } finally {
        syncingRef.current.delete(id)
        setSyncingIds([...syncingRef.current])
      }
    }))
    await load()
    if (failures.length) toast.error(failures.join("；"))
    else toast.success(pending.length === 1 ? "同步已完成" : `已同步 ${pending.length} 个仓库`)
  }

  const removeRepos = async () => {
    setDeleting(true)
    const failures: string[] = []
    for (const id of deleteIds) {
      const name = items.find((item) => item.id === id)?.name ?? String(id)
      try {
        const data = await api<{ warnings: string[] }>(`/api/repos/${id}`, { method: "DELETE" })
        if (data.warnings.length) toast.error(`${name}：${data.warnings.join("；")}`)
      } catch (caught) {
        failures.push(`${name}：${caught instanceof Error ? caught.message : "删除失败"}`)
      }
    }
    setDeleteIds([])
    await load()
    setDeleting(false)
    if (failures.length) toast.error(failures.join("；"))
    else toast.success(deleteIds.length === 1 ? "仓库已删除" : `已删除 ${deleteIds.length} 个仓库`)
  }

  const allSelected = items.length > 0 && items.every((item) => selected.includes(item.id))
  const deletingRepos = items.filter((item) => deleteIds.includes(item.id))

  return (
    <div className="space-y-6">
      <PageHeader
        title="仓库"
        description="从 Gitee 或 GitHub 拉取上游，并同步到已选目标。"
        action={<Button onClick={() => setAdding(true)}><Plus className="size-4" aria-hidden="true" />添加仓库</Button>}
      />
      <Card className="flex flex-wrap items-center gap-2 p-3">
        <Input className="max-w-xs" aria-label="搜索名称或地址" placeholder="搜索名称或地址" value={q} onChange={(event) => setQ(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void load() }} />
        <Select value={platform} onChange={(event) => setPlatform(event.target.value)} aria-label="上游平台">
          <option value="">全部平台</option>
          <option value="github">GitHub</option>
          <option value="gitee">Gitee</option>
        </Select>
        <Select value={syncStatus} onChange={(event) => setSyncStatus(event.target.value)} aria-label="同步状态">
          <option value="">全部同步状态</option>
          {Object.entries(syncLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <Select value={diffStatus} onChange={(event) => setDiffStatus(event.target.value)} aria-label="差异结果">
          <option value="">全部差异结果</option>
          {Object.entries(diffLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <Select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="排序">
          <option value="name">按名称</option>
          <option value="last_sync">按最近同步</option>
        </Select>
        <Button variant="outline" onClick={() => void load()}>搜索</Button>
        <div className="ml-auto flex gap-1">
          <Button variant={view === "grid" ? "secondary" : "outline"} aria-pressed={view === "grid"} aria-label="网格" onClick={() => changeView("grid")}><LayoutGrid className="size-4" /></Button>
          <Button variant={view === "list" ? "secondary" : "outline"} aria-pressed={view === "list"} aria-label="列表" onClick={() => changeView("list")}><List className="size-4" /></Button>
        </div>
      </Card>
      {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
      {!ready ? <p className="text-sm text-muted-foreground">正在加载仓库…</p> : items.length === 0 ? (
        <EmptyState
          icon={FolderGit2}
          title="还没有仓库"
          description="粘贴 Gitee 或 GitHub 的 HTTPS 地址，保存后会立刻做第一次同步。"
          action={<Button onClick={() => setAdding(true)}><Plus className="size-4" aria-hidden="true" />添加仓库</Button>}
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" aria-label="全选" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} />
              全选
            </label>
            <span className="text-sm text-muted-foreground">{selected.length ? `已选 ${selected.length} 个` : "可多选"}</span>
            <Button variant="outline" disabled={selected.length === 0 || deleting || selected.every((id) => syncingIds.includes(id))} onClick={() => void syncRepos(selected)}>{selected.length > 0 && selected.every((id) => syncingIds.includes(id)) ? "同步中…" : "同步"}</Button>
            <Button variant="destructive" disabled={selected.length === 0 || deleting} onClick={() => setDeleteIds(selected)}>删除</Button>
          </div>
          {view === "grid" ? (
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr))]">
              {items.map((repo) => (
                <RepoCard
                  key={repo.id}
                  repo={repo}
                  selected={selected.includes(repo.id)}
                  syncing={syncingIds.includes(repo.id)}
                  deleting={deleting}
                  onToggle={toggle}
                  onSync={() => void syncRepos([repo.id])}
                  onDelete={() => setDeleteIds([repo.id])}
                />
              ))}
            </div>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/70 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">选择</th>
                    <th className="px-4 py-3 font-medium">名称</th>
                    <th className="px-4 py-3 font-medium">上游</th>
                    <th className="px-4 py-3 font-medium">同步</th>
                    <th className="px-4 py-3 font-medium">差异</th>
                    <th className="px-4 py-3 font-medium">下次执行</th>
                    <th className="px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((repo) => (
                    <tr key={repo.id} className="border-t transition-colors hover:bg-accent/40">
                      <td className="px-4 py-3">
                        <input type="checkbox" aria-label={`选择 ${repo.name}`} checked={selected.includes(repo.id)} onChange={(event) => toggle(repo.id, event.target.checked)} />
                      </td>
                      <td className="px-4 py-3">
                        <Link className="font-medium underline-offset-2 hover:underline" to={`/repos/${repo.id}`}>{repo.name}</Link>
                        <StorageRow storages={repo.storages} />
                        <p className="max-w-md truncate text-xs text-muted-foreground">{repo.summary_excerpt || "AI未生成"}</p>
                      </td>
                      <td className="px-4 py-3"><UpstreamMark platform={repo.platform} /></td>
                      <td className="px-4 py-3"><LabeledStatus label="同步" status={repo.sync_status} labels={syncLabels} /></td>
                      <td className="px-4 py-3"><LabeledStatus label="差异" status={repo.diff_status} labels={diffLabels} hint={DIFF_HINT} /></td>
                      <td className="px-4 py-3 tabular-nums text-muted-foreground">{formatTime(repo.next_run_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <Button variant="outline" disabled={deleting || syncingIds.includes(repo.id)} aria-label={`同步 ${repo.name}`} onClick={() => void syncRepos([repo.id])}>{syncingIds.includes(repo.id) ? "同步中…" : "同步"}</Button>
                          <Button variant="destructive" disabled={deleting || syncingIds.includes(repo.id)} aria-label={`删除 ${repo.name}`} onClick={() => setDeleteIds([repo.id])}>删除</Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
      {adding ? <RepoForm key="new" open repo={null} onClose={() => setAdding(false)} onSaved={() => void load()} /> : null}
      <Modal open={deleteIds.length > 0} title="删除仓库" onClose={() => { if (!deleting) setDeleteIds([]) }}>
        <p className="text-sm leading-6">将删除{deletingRepos.map((item) => item.name).join("、") || "所选仓库"}，以及它们在每种保存方式里的内容：本地镜像、WebDAV 目录，还有 GitHub 或 Gitee 上的目标仓库。保存目标如果就是上游地址，上游会保留。</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" disabled={deleting} onClick={() => setDeleteIds([])}>取消</Button>
          <Button variant="destructive" disabled={deleting} onClick={() => void removeRepos()}>{deleting ? "删除中…" : "确认删除"}</Button>
        </div>
      </Modal>
    </div>
  )
}

function RepoCard({ repo, selected, syncing, deleting, onToggle, onSync, onDelete }: { repo: Repo; selected: boolean; syncing: boolean; deleting: boolean; onToggle: (id: number, checked: boolean) => void; onSync: () => void; onDelete: () => void }) {
  return (
    <article className="flex flex-col rounded-xl border bg-card p-5 text-card-foreground shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label={`选择 ${repo.name}`} checked={selected} onChange={(event) => onToggle(repo.id, event.target.checked)} />
          <LabeledStatus label="同步" status={repo.sync_status} labels={syncLabels} />
        </label>
      </div>
      <h2 className="mt-4 text-lg font-semibold tracking-tight">
        <Link className="hover:text-primary" to={`/repos/${repo.id}`}>{repo.name}</Link>
      </h2>
      <PlaceRow repo={repo} />
      <p className="mt-2 line-clamp-2 min-h-12 text-sm leading-6 text-muted-foreground">{repo.summary_excerpt || "AI未生成"}</p>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t pt-3">
        <LabeledStatus label="差异" status={repo.diff_status} labels={diffLabels} hint={DIFF_HINT} />
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="size-3.5" aria-hidden="true" />
          <span className="tabular-nums">{formatTime(repo.next_run_at)}</span>
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" disabled={deleting || syncing} aria-label={`同步 ${repo.name}`} onClick={onSync}>{syncing ? "同步中…" : "同步"}</Button>
        <Button variant="destructive" disabled={deleting || syncing} aria-label={`删除 ${repo.name}`} onClick={onDelete}>删除</Button>
      </div>
    </article>
  )
}

function LabeledStatus({ label, status, labels, hint }: { label: string; status: string; labels: Record<string, string>; hint?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5" title={hint}>
      {label === "差异" ? <GitCompare className="size-3.5 text-muted-foreground" aria-hidden="true" /> : null}
      <span className="text-xs text-muted-foreground">{label}</span>
      <StatusPill status={status} labels={labels} />
    </span>
  )
}

function PlaceRow({ repo }: { repo: Repo }) {
  return (
    <div className="mt-2 space-y-1.5">
      <UpstreamMark platform={repo.platform} />
      <StorageRow storages={repo.storages} />
    </div>
  )
}

function StorageRow({ storages }: { storages: StoragePlace[] }) {
  return (
    <p className="flex flex-wrap items-center gap-1" title="同步后写到这些位置">
      <span className="text-xs text-muted-foreground">保存</span>
      {storages.map((item) => <StorageMark key={`${item.type}-${item.location}`} item={item} />)}
    </p>
  )
}

function UpstreamMark({ platform }: { platform: string }) {
  return (
    <p className="flex flex-wrap items-center gap-1" title="从这个地址拉取">
      <span className="text-xs text-muted-foreground">上游</span>
      <Badge>
        <CloudDownload className="mr-1 size-3" aria-hidden="true" />
        {platformLabels[platform] ?? platform}
      </Badge>
    </p>
  )
}

function StorageMark({ item }: { item: StoragePlace }) {
  const Icon = item.type === "local" ? HardDrive : CloudUpload
  return (
    <Badge title={item.location}>
      <Icon className="mr-1 size-3" aria-hidden="true" />
      {platformLabels[item.type] ?? item.type}
    </Badge>
  )
}
