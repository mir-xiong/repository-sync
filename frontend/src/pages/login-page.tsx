import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { FolderGit2 } from "lucide-react"
import { api } from "../lib/api.ts"
import { Button } from "../components/ui/button.tsx"
import { Card } from "../components/ui/card.tsx"
import { Input, Label } from "../components/ui/input.tsx"

export function LoginPage() {
  const navigate = useNavigate()
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)

  const submit = async () => {
    setPending(true)
    setError("")
    try {
      await api("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) })
      navigate("/")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-primary-foreground/15">
            <FolderGit2 className="size-5" aria-hidden="true" />
          </span>
          <span className="font-semibold tracking-tight">仓库同步</span>
        </div>
        <div className="max-w-md">
          <p className="text-sm font-medium text-primary-foreground/70">定时镜像</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight">把上游仓库按时送到你指定的地方。</h1>
          <p className="mt-4 text-base leading-7 text-primary-foreground/80">GitHub、Gitee、WebDAV 和本地镜像共用一套调度、差异检测和同步日志。</p>
        </div>
        <p className="text-sm text-primary-foreground/70">单管理员 · 精确到分钟 · 差异只读</p>
      </section>
      <section className="flex items-center justify-center bg-background px-4 py-12 text-foreground">
        <Card className="w-full max-w-sm space-y-6 p-6 sm:p-8">
          <div className="flex items-center gap-3 lg:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground">
              <FolderGit2 className="size-5" aria-hidden="true" />
            </span>
            <span className="font-semibold">仓库同步</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">登录</h1>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">使用管理员密码进入系统。</p>
          </div>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submit()
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="password">密码</Label>
              <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
            </div>
            {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
            <Button className="w-full" type="submit" disabled={pending}>{pending ? "正在登录…" : "登录"}</Button>
          </form>
        </Card>
      </section>
    </div>
  )
}
