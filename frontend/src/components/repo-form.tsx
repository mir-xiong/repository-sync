import { useEffect, useState } from "react"
import { CircleHelp } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { api } from "../lib/api.ts"
import { platformLabels, type Repo, type RepoTarget, type Schedule, type Settings } from "../lib/types.ts"
import { cn } from "../lib/utils.ts"
import { Button } from "./ui/button.tsx"
import { Input, Label } from "./ui/input.tsx"
import { Modal } from "./ui/modal.tsx"
import { Select } from "./ui/select.tsx"

const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

const remoteTypes = ["github", "gitee", "webdav"] as const

const emptyTarget = (target_type: RepoTarget["target_type"] = "github"): RepoTarget => ({ target_type, remote_url: "" })

function repoNameFromUpstream(value: string) {
  try {
    const name = new URL(value.trim()).pathname.split("/").filter(Boolean)[1]?.replace(/\.git$/i, "") ?? ""
    return name && name !== "." && name !== ".." ? name : ""
  } catch {
    return ""
  }
}

function destinationHint(type: (typeof remoteTypes)[number], repoName: string, upstream: string) {
  if (type === "webdav") {
    return repoName ? `目录为 /拥有者/${repoName}，写在设置里的 WebDAV 地址下面。` : "目录为 /拥有者/仓库名，写在设置里的 WebDAV 地址下面。"
  }
  const place = repoName ? `保存到设置里的账户下，仓库名为 ${repoName}` : "保存到设置里的账户下，仓库名与上游相同"
  const samePlatform = (type === "github" && upstream.includes("github.com")) || (type === "gitee" && upstream.includes("gitee.com"))
  if (samePlatform) {
    return `${place}。与上游同平台时会 fork 上游，页面上会显示上游链接。`
  }
  return `${place}。账户下还没有这个仓库时，同步会先创建一个私有空仓库。`
}

const blockedReasons: Record<(typeof remoteTypes)[number], string> = {
  github: "GitHub 保存方式使用设置里的访问令牌作为账户。当前还没有保存令牌，所以不能勾选。",
  gitee: "Gitee 保存方式使用设置里的私人令牌作为账户。当前还没有保存令牌，所以不能勾选。",
  webdav: "WebDAV 保存方式使用设置里的地址和用户名作为账户。当前还没有配齐，所以不能勾选。",
}

function initialSchedule(repo?: Repo | null): Schedule {
  return (
    repo?.schedule ?? {
      type: "daily",
      time: "09:30",
      weekday: 1,
      monthday: 1,
      cron: "30 9 * * *",
      paused: false,
    }
  )
}

export function RepoForm({
  open,
  repo,
  onClose,
  onSaved,
}: {
  open: boolean
  repo?: Repo | null
  onClose: () => void
  onSaved: () => void
}) {
  const [upstream, setUpstream] = useState(repo?.upstream_url ?? "")
  const [name, setName] = useState(repo?.name ?? "")
  const [schedule, setSchedule] = useState<Schedule>(initialSchedule(repo))
  const [saveLocal, setSaveLocal] = useState(repo?.save_local ?? true)
  const [targets, setTargets] = useState<RepoTarget[]>(repo?.targets ?? [])
  const [pending, setPending] = useState(false)
  const [useProxy, setUseProxy] = useState(repo?.use_proxy ?? false)
  const [proxyConfigured, setProxyConfigured] = useState(false)
  const [proxyHelp, setProxyHelp] = useState(false)
  const [accounts, setAccounts] = useState({ ready: false, github: false, gitee: false, webdav: false })
  const [blocked, setBlocked] = useState<(typeof remoteTypes)[number] | "">("")
  const enabledRemote = (type: RepoTarget["target_type"]) => targets.some((item) => item.target_type === type)
  const accountReady = (type: (typeof remoteTypes)[number]) => accounts[type]

  useEffect(() => {
    if (!open) return
    void api<Settings>("/api/settings")
      .then((settings) => {
        setProxyConfigured(Boolean(settings.proxy_url.trim()))
        setAccounts({
          ready: true,
          github: settings.github_token_set,
          gitee: settings.gitee_token_set,
          webdav: Boolean(settings.webdav_url.trim() && settings.webdav_username.trim()),
        })
      })
      .catch((error: unknown) => toast.error(error instanceof Error ? error.message : "无法读取平台账户"))
  }, [open])

  const submit = async () => {
    setPending(true)
    const payload = {
      name: name.trim() || undefined,
      schedule: {
        type: schedule.type,
        time: schedule.type === "cron" ? null : schedule.time,
        weekday: schedule.type === "weekly" ? schedule.weekday : null,
        monthday: schedule.type === "monthly" ? schedule.monthday : null,
        cron: schedule.type === "cron" ? schedule.cron : null,
        paused: schedule.paused,
      },
      save_local: saveLocal,
      use_proxy: useProxy,
      targets: targets.map((item) => ({
        target_type: item.target_type,
        remote_url: item.remote_url.trim(),
      })),
    }
    if (!payload.save_local && payload.targets.length === 0) {
      toast.error("至少选择一种保存方式")
      setPending(false)
      return
    }
    try {
      if (repo) {
        await api(`/api/repos/${repo.id}`, { method: "PATCH", body: JSON.stringify(payload) })
        toast.success("仓库已更新")
      } else {
        const created = await api<{ summary_error: string | null }>("/api/repos", {
          method: "POST",
          body: JSON.stringify({ ...payload, upstream_url: upstream.trim() }),
        })
        toast.success(created.summary_error ? `仓库已添加，概要未生成：${created.summary_error}` : "仓库已添加并完成首次同步")
      }
      onSaved()
      onClose()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败")
    } finally {
      setPending(false)
    }
  }

  return (
    <Modal open={open} title={repo ? "编辑仓库" : "添加仓库"} onClose={onClose}>
      <div className="space-y-4">
        {repo ? null : (
          <div className="space-y-1">
            <Label htmlFor="upstream">上游 HTTPS 地址</Label>
            <Input id="upstream" value={upstream} onChange={(event) => setUpstream(event.target.value)} placeholder="https://github.com/owner/repo" />
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="repo-name">显示名称</Label>
          <Input id="repo-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="默认使用拥有者/仓库名" />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="schedule-type">调度</Label>
            <Select id="schedule-type" className="w-full" value={schedule.type} onChange={(event) => setSchedule({ ...schedule, type: event.target.value as Schedule["type"], weekday: schedule.weekday ?? 1, monthday: schedule.monthday ?? 1, time: schedule.time ?? "09:30", cron: schedule.cron ?? "30 9 * * *" })}>
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="monthly">每月</option>
              <option value="cron">Cron</option>
            </Select>
          </div>
          {schedule.type === "cron" ? (
            <div className="space-y-1">
              <Label htmlFor="cron">Cron（分 时 日 月 周）</Label>
              <Input id="cron" value={schedule.cron ?? ""} onChange={(event) => setSchedule({ ...schedule, cron: event.target.value })} />
            </div>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="clock">时间</Label>
              <Input id="clock" type="time" value={schedule.time ?? "09:30"} onChange={(event) => setSchedule({ ...schedule, time: event.target.value })} />
            </div>
          )}
          {schedule.type === "weekly" ? (
            <div className="space-y-1">
              <Label htmlFor="weekday">星期</Label>
              <Select id="weekday" className="w-full" value={schedule.weekday ?? 1} onChange={(event) => setSchedule({ ...schedule, weekday: Number(event.target.value) })}>
                {weekdays.map((label, index) => (
                  <option key={label} value={index + 1}>{label}</option>
                ))}
              </Select>
            </div>
          ) : null}
          {schedule.type === "monthly" ? (
            <div className="space-y-1">
              <Label htmlFor="monthday">日期</Label>
              <Input id="monthday" type="number" min={1} max={31} value={schedule.monthday ?? 1} onChange={(event) => setSchedule({ ...schedule, monthday: Number(event.target.value) })} />
            </div>
          ) : null}
        </div>
        {repo ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={schedule.paused} onChange={(event) => setSchedule({ ...schedule, paused: event.target.checked })} />
            暂停定时同步
          </label>
        ) : null}
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium">保存方式</legend>
          <p className="text-sm text-muted-foreground">可以多选。本地默认保存。GitHub、Gitee 和 WebDAV 使用设置里的账户，位置按上游仓库自动确定，不用填写地址。未配置的账户不能勾选。</p>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={saveLocal} onChange={(event) => setSaveLocal(event.target.checked)} />
            本地
          </label>
          {remoteTypes.map((type) => {
            const configured = accountReady(type)
            const checked = enabledRemote(type)
            const saved = targets.find((item) => item.target_type === type)
            const repoName = repo?.repo_name || repoNameFromUpstream(upstream)
            return (
              <div key={type} className="space-y-1">
                <div className="flex min-h-11 items-center gap-1 text-sm">
                  <label className={cn("flex items-center gap-2", configured || checked ? "" : "text-muted-foreground")}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!accounts.ready || (!configured && !checked)}
                      onChange={(event) => {
                        if (event.target.checked) {
                          if (!configured) return
                          setTargets([...targets, emptyTarget(type)])
                        } else {
                          setTargets(targets.filter((item) => item.target_type !== type))
                        }
                      }}
                    />
                    {platformLabels[type]}
                  </label>
                  {accounts.ready && !configured ? (
                    <Button type="button" variant="ghost" className="size-11 px-0 text-muted-foreground" aria-label={`查看无法勾选${platformLabels[type]}的原因`} onClick={() => setBlocked(type)}>
                      <CircleHelp className="size-4" aria-hidden="true" />
                    </Button>
                  ) : null}
                </div>
                {checked ? <p className="pl-6 text-sm text-muted-foreground">{saved?.remote_url ? `位置：${saved.remote_url}` : destinationHint(type, repoName, repo?.upstream_url || upstream)}</p> : null}
              </div>
            )
          })}
        </fieldset>
        <div className="flex min-h-11 items-center gap-1 text-sm">
          <label className={cn("flex items-center gap-2", proxyConfigured || useProxy ? "" : "text-muted-foreground")}>
            <input
              type="checkbox"
              checked={useProxy}
              disabled={!proxyConfigured && !useProxy}
              onChange={(event) => {
                if (event.target.checked && !proxyConfigured) return
                setUseProxy(event.target.checked)
              }}
            />
            通过设置中的代理访问
          </label>
          {!proxyConfigured && !useProxy ? (
            <Button type="button" variant="ghost" className="size-11 px-0 text-muted-foreground" aria-label="查看无法使用代理的原因" onClick={() => setProxyHelp(true)}>
              <CircleHelp className="size-4" aria-hidden="true" />
            </Button>
          ) : null}
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>取消</Button>
          <Button type="button" disabled={pending} onClick={() => void submit()}>{pending ? "正在同步…" : "保存"}</Button>
        </div>
        {pending && !repo ? <p className="text-sm text-muted-foreground">正在拉取上游，仓库较大时会久一点。</p> : null}
      </div>
      <Modal open={Boolean(blocked)} title={blocked ? `无法勾选 ${platformLabels[blocked]}` : "无法勾选"} onClose={() => setBlocked("")}>
        <p className="text-sm leading-6">{blocked ? blockedReasons[blocked] : ""}</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setBlocked("")}>关闭</Button>
          <Button asChild>
            <Link to="/settings" onClick={onClose}>前往设置</Link>
          </Button>
        </div>
      </Modal>
      <Modal open={proxyHelp} title="还不能使用代理" onClose={() => setProxyHelp(false)}>
        <p className="text-sm leading-6">拉取、推送和 WebDAV 会走设置里保存的代理。当前还没有保存代理地址，所以不能勾选。</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setProxyHelp(false)}>关闭</Button>
          <Button asChild>
            <Link to="/settings" onClick={onClose}>前往设置</Link>
          </Button>
        </div>
      </Modal>
    </Modal>
  )
}
