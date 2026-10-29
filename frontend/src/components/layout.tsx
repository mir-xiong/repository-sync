import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { FolderGit2, LogOut, ScrollText, Settings } from "lucide-react"
import { toast } from "sonner"
import { api } from "../lib/api.ts"
import { cn } from "../lib/utils.ts"
import { ThemePresetSelector } from "./theme-preset-selector.tsx"
import { Button } from "./ui/button.tsx"

const links = [
  { to: "/", label: "仓库", end: true, icon: FolderGit2 },
  { to: "/logs", label: "日志", end: false, icon: ScrollText },
  { to: "/settings", label: "设置", end: false, icon: Settings },
]

export function Layout() {
  const navigate = useNavigate()
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" })
    toast.success("已退出")
    navigate("/login")
  }
  return (
    <div className="min-h-svh lg:grid lg:grid-cols-[16rem_1fr]">
      <aside className="sticky top-0 hidden h-svh flex-col border-r bg-sidebar text-sidebar-foreground lg:flex">
        <div className="flex items-center gap-3 px-5 py-6">
          <BrandMark />
          <div>
            <p className="font-semibold tracking-tight">仓库同步</p>
            <p className="text-xs text-sidebar-foreground/70">镜像与调度</p>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {links.map((link) => (
            <SideLink key={link.to} {...link} />
          ))}
        </nav>
        <div className="space-y-2 border-t border-sidebar-border p-3">
          <ThemePresetSelector placement="top-start" />
          <Button variant="ghost" className="w-full justify-start text-sidebar-foreground" onClick={() => void logout()}>
            <LogOut className="size-4" aria-hidden="true" />
            退出
          </Button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex items-center gap-2">
              <BrandMark />
              <span className="font-semibold">仓库同步</span>
            </div>
            <ThemePresetSelector />
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-3">
            {links.map((link) => (
              <SideLink key={link.to} {...link} compact />
            ))}
            <Button variant="ghost" className="shrink-0" onClick={() => void logout()}>退出</Button>
          </nav>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function BrandMark() {
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground">
      <FolderGit2 className="size-4" aria-hidden="true" />
    </span>
  )
}

function SideLink({
  to,
  label,
  end,
  icon: Icon,
  compact = false,
}: {
  to: string
  label: string
  end: boolean
  icon: typeof FolderGit2
  compact?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "inline-flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors duration-200",
          compact ? "shrink-0" : "w-full",
          isActive
            ? compact
              ? "bg-accent text-accent-foreground"
              : "bg-sidebar-accent text-sidebar-accent-foreground"
            : compact
              ? "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              : "text-sidebar-foreground/75 hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </NavLink>
  )
}
