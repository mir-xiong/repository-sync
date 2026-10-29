import { useEffect, useState, type ReactNode } from "react"
import { Bot, CircleHelp, Eye, EyeOff, Folder, FolderOpen, Globe, KeyRound, Palette, RefreshCw, SlidersHorizontal } from "lucide-react"
import { toast } from "sonner"
import { api } from "../lib/api.ts"
import { cn } from "../lib/utils.ts"
import type { Provider, Settings } from "../lib/types.ts"
import { PageHeader } from "../components/page-header.tsx"
import { ThemePresetSelector } from "../components/theme-preset-selector.tsx"
import { Button } from "../components/ui/button.tsx"
import { Card } from "../components/ui/card.tsx"
import { Input, Label } from "../components/ui/input.tsx"
import { Modal } from "../components/ui/modal.tsx"
import { Select } from "../components/ui/select.tsx"

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [retention, setRetention] = useState(7)
  const [concurrency, setConcurrency] = useState(2)
  const [localDir, setLocalDir] = useState("")
  const [directoryPrompt, setDirectoryPrompt] = useState("")
  const [picking, setPicking] = useState(false)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [githubToken, setGithubToken] = useState("")
  const [giteeToken, setGiteeToken] = useState("")
  const [webdavUrl, setWebdavUrl] = useState("")
  const [webdavUsername, setWebdavUsername] = useState("")
  const [webdavPassword, setWebdavPassword] = useState("")
  const [testing, setTesting] = useState("")
  const [tokenHelp, setTokenHelp] = useState<"github" | "gitee" | "">("")
  const [providers, setProviders] = useState<Provider[]>([])
  const [editor, setEditor] = useState<null | { mode: "create" | "edit"; id?: number }>(null)
  const [draft, setDraft] = useState(emptyProviderDraft)
  const [showDraftKey, setShowDraftKey] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [proxyUrl, setProxyUrl] = useState("")
  const [testingProxy, setTestingProxy] = useState(false)
  const [revealed, setRevealed] = useState<{ name: string; apiKey: string } | null>(null)

  const load = async () => {
    const [nextSettings, nextProviders] = await Promise.all([
      api<Settings>("/api/settings"),
      api<{ items: Provider[] }>("/api/ai/providers"),
    ])
    setSettings(nextSettings)
    setRetention(nextSettings.log_retention_days)
    setConcurrency(nextSettings.sync_concurrency)
    setLocalDir(nextSettings.local_mirror_dir)
    setProxyUrl(nextSettings.proxy_url)
    setWebdavUrl(nextSettings.webdav_url)
    setWebdavUsername(nextSettings.webdav_username)
    setProviders(nextProviders.items)
  }

  useEffect(() => {
    void load().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "加载失败"))
  }, [])

  const browseDirectory = async () => {
    setPicking(true)
    try {
      const data = await api<{ path: string | null }>("/api/settings/local-directory/browse", { method: "POST" })
      if (!data.path || !settings) return
      setLocalDir(data.path)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "无法打开目录选择窗口")
    } finally {
      setPicking(false)
    }
  }

  const askDirectory = () => {
    const next = localDir.trim()
    if (!settings || next === settings.local_mirror_dir) {
      toast.success("本地目录没有变化")
      return
    }
    setDirectoryPrompt(next)
  }

  const applyDirectory = async (migrate: boolean) => {
    const data = await api<Settings & { migrated: boolean; removed: Array<{ name: string }> }>("/api/settings/local-directory", {
      method: "POST",
      body: JSON.stringify({ path: directoryPrompt, migrate }),
    })
    setSettings(data)
    setLocalDir(data.local_mirror_dir)
    setDirectoryPrompt("")
    if (migrate) {
      toast.success("本地镜像已同步到新目录")
      return
    }
    const names = data.removed.map((item) => item.name).join("、")
    toast.success(names ? `已切换目录，并移除只保存在本地的仓库：${names}` : "已切换目录，相关仓库的保存方式已更新")
  }

  const saveSystem = async () => {
    const data = await api<Settings>("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ log_retention_days: retention, sync_concurrency: concurrency }),
    })
    setSettings(data)
    toast.success("系统设置已保存")
  }

  const changePassword = async () => {
    await api("/api/auth/password", { method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) })
    setCurrentPassword("")
    setNewPassword("")
    toast.success("密码已修改，其他会话已失效")
  }

  const saveCredential = async (body: Record<string, unknown>, clear: () => void, message: string) => {
    const data = await api<Settings>("/api/settings/credentials", { method: "PATCH", body: JSON.stringify(body) })
    setSettings(data)
    setWebdavUrl(data.webdav_url)
    setWebdavUsername(data.webdav_username)
    clear()
    toast.success(message)
  }

  const testCredential = async (target: "github" | "gitee" | "webdav") => {
    setTesting(target)
    try {
      await api("/api/settings/credentials/test", { method: "POST", body: JSON.stringify({ target }) })
      toast.success("连接成功")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "连接失败")
    } finally {
      setTesting("")
    }
  }

  const resetEditor = () => {
    setEditor(null)
    setDraft(emptyProviderDraft())
    setModels([])
    setShowDraftKey(false)
  }

  const startCreate = () => {
    setDraft(emptyProviderDraft())
    setModels([])
    setShowDraftKey(false)
    setEditor({ mode: "create" })
  }

  const startEdit = async (provider: Provider) => {
    const secret = await api<{ api_key: string }>(`/api/ai/providers/${provider.id}/secret`)
    setDraft({
      name: provider.name,
      base_url: provider.base_url,
      api_key: secret.api_key,
      model: provider.model,
      enabled: provider.enabled,
      use_proxy: provider.use_proxy,
    })
    setModels([])
    setShowDraftKey(false)
    setEditor({ mode: "edit", id: provider.id })
  }

  const copyProvider = async (provider: Provider) => {
    const secret = await api<{ api_key: string }>(`/api/ai/providers/${provider.id}/secret`)
    await api("/api/ai/providers", {
      method: "POST",
      body: JSON.stringify({
        name: `${provider.name} 副本`.slice(0, 120),
        base_url: provider.base_url,
        api_key: secret.api_key,
        model: provider.model,
        enabled: false,
        use_proxy: provider.use_proxy,
      }),
    })
    await load()
    toast.success("已复制一份，默认不启用")
  }

  const saveProvider = async () => {
    if (!editor) return
    if (editor.mode === "create") {
      await api("/api/ai/providers", { method: "POST", body: JSON.stringify(draft) })
    } else {
      const body: Record<string, unknown> = {
        name: draft.name,
        base_url: draft.base_url,
        model: draft.model,
        enabled: draft.enabled,
        use_proxy: draft.use_proxy,
      }
      if (draft.api_key.trim()) body.api_key = draft.api_key.trim()
      await api(`/api/ai/providers/${editor.id}`, { method: "PATCH", body: JSON.stringify(body) })
    }
    resetEditor()
    await load()
    toast.success("厂商已保存")
  }

  const saveProxy = async () => {
    const data = await api<Settings>("/api/settings", { method: "PATCH", body: JSON.stringify({ proxy_url: proxyUrl.trim() }) })
    setSettings(data)
    setProxyUrl(data.proxy_url)
    toast.success(data.proxy_url ? "代理已保存" : "已清除代理")
  }

  const testProxy = async () => {
    setTestingProxy(true)
    try {
      await api("/api/settings/proxy/test", { method: "POST", body: JSON.stringify({ proxy_url: proxyUrl.trim() }) })
      toast.success("代理可以连通")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "代理连接失败")
    } finally {
      setTestingProxy(false)
    }
  }

  const loadModels = async () => {
    if (!draft.base_url.trim()) {
      toast.error("请先填写接口地址")
      return
    }
    setLoadingModels(true)
    try {
      const data = await api<{ items: string[] }>("/api/ai/models", {
        method: "POST",
        body: JSON.stringify({
          base_url: draft.base_url.trim(),
          api_key: draft.api_key,
          use_proxy: draft.use_proxy,
          provider_id: editor?.mode === "edit" && !draft.api_key.trim() ? editor.id : undefined,
        }),
      })
      setModels(data.items)
      setDraft((current) => ({ ...current, model: current.model || data.items[0] || "" }))
      toast.success(`已获取 ${data.items.length} 个模型`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "获取模型失败")
    } finally {
      setLoadingModels(false)
    }
  }

  const revealKey = async (provider: Provider) => {
    const data = await api<{ api_key: string }>(`/api/ai/providers/${provider.id}/secret`)
    setRevealed({ name: provider.name, apiKey: data.api_key })
  }

  if (!settings) return <p className="text-sm text-muted-foreground">正在加载设置…</p>

  return (
    <div className="space-y-6">
      <PageHeader title="设置" description="主题、代理、凭证和概要模型都在这里。" />
      <Section icon={Palette} title="主题" description="和侧栏使用同一套偏好，只保存在这台浏览器。">
        <div className="max-w-sm">
          <ThemePresetSelector />
        </div>
      </Section>
      <Section icon={SlidersHorizontal} title="系统" description="日志默认保留 7 天，最长 180 天。同一时刻最多并行同步 8 个仓库。">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="retention">日志保留天数（1–180）</Label>
            <Input id="retention" type="number" min={1} max={180} value={retention} onChange={(event) => setRetention(Number(event.target.value))} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="concurrency">同步并行数</Label>
            <Input id="concurrency" type="number" min={1} max={8} value={concurrency} onChange={(event) => setConcurrency(Number(event.target.value))} />
          </div>
        </div>
        <Button className="w-fit" onClick={() => void saveSystem().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "保存失败"))}>保存系统设置</Button>
      </Section>
      <Section icon={Folder} title="本地目录" description="选择「本地」保存方式的仓库会放在这台电脑的这个文件夹里。可以从系统窗口选择，也可以直接填写路径。">
        <div className="space-y-1.5">
          <Label htmlFor="local-dir">镜像目录</Label>
          <div className="flex gap-2">
            <Input id="local-dir" className="font-mono" value={localDir} onChange={(event) => setLocalDir(event.target.value)} />
            <Button type="button" variant="outline" className="shrink-0" disabled={picking} onClick={() => void browseDirectory()}>
              <FolderOpen className="size-4" aria-hidden="true" />
              {picking ? "请在窗口中选择…" : "选择目录"}
            </Button>
          </div>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">选择或填写后先点保存，再决定是否把现有镜像同步到新目录。</p>
        <Button className="w-fit" disabled={picking} onClick={askDirectory}>保存</Button>
      </Section>
      <Section icon={Globe} title="代理" description="只支持 http 和 https。仓库和 AI 厂商可以各自选择是否走这里保存的代理。">
        <div className="space-y-1.5">
          <Label htmlFor="proxy-url">代理地址</Label>
          <Input id="proxy-url" className="font-mono" value={proxyUrl} placeholder="http://127.0.0.1:7890" onChange={(event) => setProxyUrl(event.target.value)} />
        </div>
        <p className="text-sm leading-6 text-muted-foreground">留空后保存会清除代理。测试会经代理访问 GitHub 首页。</p>
        <div className="flex flex-wrap gap-2">
          <Button className="w-fit" onClick={() => void saveProxy().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "保存失败"))}>保存</Button>
          <Button variant="outline" className="w-fit" disabled={testingProxy} onClick={() => void testProxy()}>
            {testingProxy ? "测试中…" : "测试"}
          </Button>
        </div>
      </Section>
      <Modal open={Boolean(directoryPrompt)} title="更换本地目录" onClose={() => setDirectoryPrompt("")}>
        <p className="text-sm leading-6">是否把现有本地镜像同步到新目录？</p>
        <p className="mt-2 break-all font-mono text-xs text-muted-foreground">{directoryPrompt}</p>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">不同步时，只保存在本地的仓库会从列表移除，镜像文件仍留在原目录。同时保存到其他位置的仓库会去掉「本地」这一项。</p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setDirectoryPrompt("")}>取消</Button>
          <Button variant="outline" onClick={() => void applyDirectory(false).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "切换失败"))}>不同步</Button>
          <Button onClick={() => void applyDirectory(true).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "同步失败"))}>同步到新目录</Button>
        </div>
      </Modal>
      <Section icon={KeyRound} title="修改密码" description="修改后其他已登录的浏览器会退出。">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="current-password">当前密码</Label>
            <Input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-password">新密码，至少 8 位</Label>
            <Input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} />
          </div>
        </div>
        <Button className="w-fit" onClick={() => void changePassword().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "修改失败"))}>修改密码</Button>
      </Section>
      <Section icon={KeyRound} title="平台凭证" description="公开仓库只保存在本地时不用令牌。私有仓库，或保存方式里有 GitHub、Gitee，才需要下面的令牌。密钥不会回显；测试使用的是已经保存的凭证。">
        <div className="grid gap-3">
          <CredentialPanel title="GitHub" hint="公开仓库只保存在本地时不用填。私有仓库，或要在 GitHub 上创建、fork、推送、删除，点问号看要勾的权限。" configured={settings.github_token_set}>
            <SecretField id="github" label="访问令牌" helpLabel="查看 GitHub 令牌创建说明" onHelp={() => setTokenHelp("github")} value={githubToken} onChange={setGithubToken} configured={settings.github_token_set} />
            <CredentialActions
              testing={testing === "github"}
              canTest={settings.github_token_set}
              canClear={settings.github_token_set}
              onSave={() => {
                if (!githubToken.trim()) {
                  toast.error("请填写新的 GitHub 令牌；留空不会改掉已保存的值")
                  return
                }
                return saveCredential({ github_token: githubToken.trim() }, () => setGithubToken(""), "GitHub 令牌已保存")
              }}
              onTest={() => testCredential("github")}
              onClear={() => saveCredential({ clear_github_token: true }, () => setGithubToken(""), "已清除 GitHub 令牌")}
            />
          </CredentialPanel>
          <CredentialPanel title="Gitee" hint="公开仓库只保存在本地时不用填。私有仓库，或要在 Gitee 上创建、fork、推送、删除，点问号看要勾的权限。" configured={settings.gitee_token_set}>
            <SecretField id="gitee" label="私人令牌" helpLabel="查看 Gitee 令牌创建说明" onHelp={() => setTokenHelp("gitee")} value={giteeToken} onChange={setGiteeToken} configured={settings.gitee_token_set} />
            <CredentialActions
              testing={testing === "gitee"}
              canTest={settings.gitee_token_set}
              canClear={settings.gitee_token_set}
              onSave={() => {
                if (!giteeToken.trim()) {
                  toast.error("请填写新的 Gitee 令牌；留空不会改掉已保存的值")
                  return
                }
                return saveCredential({ gitee_token: giteeToken.trim() }, () => setGiteeToken(""), "Gitee 令牌已保存")
              }}
              onTest={() => testCredential("gitee")}
              onClear={() => saveCredential({ clear_gitee_token: true }, () => setGiteeToken(""), "已清除 Gitee 令牌")}
            />
          </CredentialPanel>
          <CredentialPanel title="WebDAV" hint="上传默认分支工作区时使用。地址、用户名会保留在页面上，密码只显示是否已保存。" configured={Boolean(settings.webdav_url || settings.webdav_password_set)}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="webdav-url">地址</Label>
                <Input id="webdav-url" value={webdavUrl} onChange={(event) => setWebdavUrl(event.target.value)} placeholder="https://example.com/remote.php/webdav" autoComplete="off" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="webdav-user">用户名</Label>
                <Input id="webdav-user" value={webdavUsername} onChange={(event) => setWebdavUsername(event.target.value)} autoComplete="off" />
              </div>
              <SecretField id="webdav-pass" label="密码" value={webdavPassword} onChange={setWebdavPassword} configured={settings.webdav_password_set} />
            </div>
            <CredentialActions
              testing={testing === "webdav"}
              canTest={Boolean(settings.webdav_url)}
              canClear={Boolean(settings.webdav_url || settings.webdav_username || settings.webdav_password_set)}
              saveLabel="保存 WebDAV"
              clearLabel="清除"
              onSave={() => saveCredential(
                { webdav_url: webdavUrl.trim(), webdav_username: webdavUsername.trim(), webdav_password: webdavPassword || null },
                () => setWebdavPassword(""),
                "WebDAV 已保存",
              )}
              onTest={() => testCredential("webdav")}
              onClear={() => saveCredential(
                { webdav_url: "", webdav_username: "", clear_webdav_password: true },
                () => { setWebdavUrl(""); setWebdavUsername(""); setWebdavPassword("") },
                "已清除 WebDAV",
              )}
            />
          </CredentialPanel>
        </div>
      </Section>
      <Modal open={tokenHelp === "github"} title="创建 GitHub 令牌" onClose={() => setTokenHelp("")}>
        <div className="space-y-4 text-sm leading-6">
          <p>公开仓库并且只保存在本地时，不用令牌。程序用 HTTPS 直接拉取，这台电脑不用另外登录 GitHub。</p>
          <p>上游是私有仓库时，即使只保存在本地也要令牌，否则拉不下来。保存方式里有 GitHub 时，创建、fork、推送分支和标签，以及在这里删除仓库时删掉 GitHub 上的目标，都用这份令牌。勾选本地不会代替它。</p>
          <div className="space-y-2">
            <p className="font-medium">细粒度令牌要开的权限</p>
            <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
              <li>Contents：Read and write。读取私有仓库，并推送分支和标签。</li>
              <li>Administration：Read and write。在你的账户下新建仓库、fork，以及删除保存到 GitHub 的仓库。同平台同步时，已有的同名普通仓库要先删掉再 fork，也靠这项。</li>
              <li>Repository creation 可以不选。它只代替 Administration 里的「新建和 fork」，不能删除仓库。创建页的权限列表里如果搜不到这一项，保持不选即可。</li>
            </ul>
            <p className="text-muted-foreground">仓库访问选 All repositories。只选部分仓库时，新建或 fork 出来的仓库不在范围内，接着推送和删除都会失败。Metadata 会自动变成只读。令牌只在生成时显示一次。</p>
            <Button asChild className="w-fit">
              <a href="https://github.com/settings/personal-access-tokens/new?name=repository-sync&description=Pull%2C+fork%2C+push+and+delete+mirrors&contents=write&administration=write" target="_blank" rel="noreferrer">打开创建页面</a>
            </Button>
          </div>
          <div className="space-y-2">
            <p className="font-medium">经典令牌</p>
            <p className="text-muted-foreground">勾选 <span className="font-mono">repo</span>。它包含读取、推送、创建、fork 和删除，并覆盖你能访问的全部分库。</p>
            <Button asChild variant="outline" className="w-fit">
              <a href="https://github.com/settings/tokens/new?scopes=repo&description=repository-sync" target="_blank" rel="noreferrer">打开经典令牌页面</a>
            </Button>
          </div>
          <a className="inline-block text-primary underline-offset-4 hover:underline" href="https://docs.github.com/zh/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens" target="_blank" rel="noreferrer">GitHub 官方说明</a>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setTokenHelp("")}>关闭</Button>
          </div>
        </div>
      </Modal>
      <Modal open={tokenHelp === "gitee"} title="创建 Gitee 私人令牌" onClose={() => setTokenHelp("")}>
        <div className="space-y-4 text-sm leading-6">
          <p>公开仓库并且只保存在本地时，不用私人令牌。程序用 HTTPS 直接拉取，这台电脑不用另外登录 Gitee。</p>
          <p>上游是私有仓库时，即使只保存在本地也要令牌，否则拉不下来。保存方式里有 Gitee 时，创建、fork、推送，以及在这里删除仓库时删掉 Gitee 上的目标，都用这份令牌。勾选本地不会代替它。</p>
          <p>在 Gitee 里走：头像 → 设置 → 安全设置 → 私人令牌 → 生成新令牌。提交时要输入登录密码，令牌只显示一次。</p>
          <p>Gitee 的生成新令牌页面会默认勾选全部权限。下面的链接只打开这个页面，地址里没有权限参数，也改不了这个默认。提交前请取消多余项，只保留下面两项。</p>
          <Button asChild className="w-fit">
            <a href="https://gitee.com/profile/personal_access_tokens/new" target="_blank" rel="noreferrer">打开创建页面</a>
          </Button>
          <div className="space-y-2">
            <p className="font-medium">只保留这两项</p>
            <ul className="list-disc space-y-1 pl-5">
              <li><span className="font-mono">user_info</span>：读取当前账户。这里的「测试连接」会用到。这一项 Gitee 会保持勾选。</li>
              <li><span className="font-mono">projects</span>：读取私有仓库、推送、在你的账户下创建或 fork，以及删除保存到 Gitee 的仓库。Gitee 没有单独的 Administration 权限，这些都在这一项里。</li>
            </ul>
            <p className="text-muted-foreground">issues、pull_requests、notes、keys、hook、groups、gists、enterprises 等请取消勾选。</p>
          </div>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setTokenHelp("")}>关闭</Button>
          </div>
        </div>
      </Modal>
      <Section icon={Bot} title="AI 厂商" description="可以添加多个，同时只有一个启用。点添加后再填写，已添加的可以编辑和复制。接口使用 OpenAI 兼容的 /v1。">
        {providers.length === 0 ? <p className="text-sm text-muted-foreground">还没有 AI 厂商。</p> : null}
        {providers.map((provider) => (
          <div key={provider.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
            <div>
              <p className="font-medium">{provider.name} {provider.enabled ? "· 生效中" : ""}{provider.use_proxy ? " · 使用代理" : ""}</p>
              <p className="text-muted-foreground">{provider.base_url} · {provider.model}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => void startEdit(provider).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "无法编辑"))}>编辑</Button>
              <Button variant="outline" onClick={() => void copyProvider(provider).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "复制失败"))}>复制</Button>
              <Button variant="outline" onClick={() => void revealKey(provider).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "无法查看密钥"))}>查看密钥</Button>
              <Button variant="outline" onClick={() => void api(`/api/ai/providers/${provider.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !provider.enabled }) }).then(load)}>
                {provider.enabled ? "停用" : "启用"}
              </Button>
              <Button variant="outline" onClick={() => void api(`/api/ai/providers/${provider.id}/test`, { method: "POST" }).then(() => toast.success("连接成功")).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "失败"))}>测试</Button>
              <Button variant="ghost" disabled={provider.enabled} onClick={() => void api(`/api/ai/providers/${provider.id}`, { method: "DELETE" }).then(load).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "删除失败"))}>{provider.enabled ? "启用中不可删" : "删除"}</Button>
            </div>
          </div>
        ))}
        {editor ? (
          <div className="space-y-3 rounded-xl border bg-muted/30 p-4">
            <h3 className="font-medium">{editor.mode === "create" ? "新建厂商" : "编辑厂商"}</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input className="sm:col-span-2" placeholder="名称" aria-label="厂商名称" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              <Input placeholder="接口地址" aria-label="接口地址" value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} />
              <div className="flex gap-2">
                <Input className="min-w-0 flex-1" placeholder="密钥" aria-label="密钥" type={showDraftKey ? "text" : "password"} value={draft.api_key} onChange={(event) => setDraft({ ...draft, api_key: event.target.value })} />
                <Button type="button" variant="outline" className="shrink-0 px-3" aria-label={showDraftKey ? "隐藏密钥" : "显示密钥"} onClick={() => setShowDraftKey((value) => !value)}>
                  {showDraftKey ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
                </Button>
              </div>
              <div className="flex gap-2 sm:col-span-2">
                <Input className="min-w-0 flex-1" placeholder="模型" aria-label="模型" value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })} />
                <Button type="button" variant="outline" className="shrink-0 px-3" aria-label="获取模型" disabled={loadingModels} onClick={() => void loadModels()}>
                  <RefreshCw className={cn("size-4", loadingModels && "animate-spin")} aria-hidden="true" />
                </Button>
              </div>
            </div>
            {models.length > 0 ? (
              <div className="space-y-1.5">
                <Label htmlFor="model-list">模型列表</Label>
                <Select id="model-list" className="w-full" value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })}>
                  {models.map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </Select>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />
                {editor.mode === "create" ? "添加后立即启用" : "启用"}
              </label>
              <label className={cn("flex items-center gap-2 text-sm", settings.proxy_url.trim() || draft.use_proxy ? "" : "text-muted-foreground")}>
                <input
                  type="checkbox"
                  checked={draft.use_proxy}
                  disabled={!settings.proxy_url.trim() && !draft.use_proxy}
                  onChange={(event) => setDraft({ ...draft, use_proxy: event.target.checked })}
                />
                通过设置中的代理访问
              </label>
            </div>
            {!settings.proxy_url.trim() ? <p className="text-sm text-muted-foreground">还没有保存代理地址，不能勾选代理。</p> : null}
            {editor.mode === "edit" ? <p className="text-sm text-muted-foreground">清空密钥再保存，会保留原来的密钥。</p> : null}
            <div className="flex flex-wrap gap-2">
              <Button className="w-fit" onClick={() => void saveProvider().catch((error: unknown) => toast.error(error instanceof Error ? error.message : "保存失败"))}>保存</Button>
              <Button variant="outline" className="w-fit" onClick={resetEditor}>取消</Button>
            </div>
          </div>
        ) : (
          <Button className="w-fit" onClick={startCreate}>添加 AI 厂商</Button>
        )}
      </Section>
      <Modal open={Boolean(revealed)} title={revealed ? `${revealed.name} 的密钥` : "密钥"} onClose={() => setRevealed(null)}>
        <p className="break-all font-mono text-sm">{revealed?.apiKey || "（空）"}</p>
        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={() => setRevealed(null)}>关闭</Button>
        </div>
      </Modal>
    </div>
  )
}

function emptyProviderDraft() {
  return { name: "", base_url: "https://api.openai.com/v1", api_key: "", model: "", enabled: false, use_proxy: false }
}

function CredentialPanel({ title, hint, configured, children }: { title: string; hint: string; configured: boolean; children: ReactNode }) {
  return (
    <div className="rounded-xl border bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-medium">{title}</h3>
        <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium", configured ? "border-chart-2/40" : "text-muted-foreground")}>
          <span className={cn("size-1.5 rounded-full", configured ? "bg-chart-2" : "bg-muted-foreground")} aria-hidden="true" />
          {configured ? "已配置" : "未配置"}
        </span>
      </div>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">{hint}</p>
      <div className="mt-4 space-y-3">{children}</div>
    </div>
  )
}

function SecretField({ id, label, value, onChange, configured, onHelp, helpLabel }: { id: string; label: string; value: string; onChange: (value: string) => void; configured: boolean; onHelp?: () => void; helpLabel?: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1">
        <Label htmlFor={id}>{label}</Label>
        {onHelp ? (
          <Button type="button" variant="ghost" className="size-11 px-0 text-muted-foreground" aria-label={helpLabel} onClick={onHelp}>
            <CircleHelp className="size-4" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <div className="flex gap-2">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          value={value}
          placeholder={configured ? "已保存，留空则不修改" : "粘贴新的密钥"}
          onChange={(event) => onChange(event.target.value)}
        />
        <Button type="button" variant="outline" className="shrink-0 px-3" aria-pressed={visible} aria-label={visible ? "隐藏密钥" : "显示密钥"} onClick={() => setVisible((current) => !current)}>
          {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
        </Button>
      </div>
    </div>
  )
}

function CredentialActions({
  testing,
  canTest,
  canClear,
  saveLabel = "保存",
  clearLabel = "清除令牌",
  onSave,
  onTest,
  onClear,
}: {
  testing: boolean
  canTest: boolean
  canClear: boolean
  saveLabel?: string
  clearLabel?: string
  onSave: () => void | Promise<void>
  onTest: () => void | Promise<void>
  onClear: () => void | Promise<void>
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button onClick={() => void Promise.resolve(onSave()).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "保存失败"))}>{saveLabel}</Button>
      <Button variant="outline" disabled={!canTest || testing} onClick={() => void Promise.resolve(onTest())}>{testing ? "测试中…" : "测试连接"}</Button>
      {canClear ? <Button variant="ghost" onClick={() => void Promise.resolve(onClear()).catch((error: unknown) => toast.error(error instanceof Error ? error.message : "清除失败"))}>{clearLabel}</Button> : null}
    </div>
  )
}

function Section({ icon: Icon, title, description, children }: { icon: typeof Palette; title: string; description: string; children: ReactNode }) {
  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-4" aria-hidden="true" />
        </span>
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
      </div>
      {children}
    </Card>
  )
}
