import { useEffect, useState } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { api } from "./lib/api.ts"
import { Layout } from "./components/layout.tsx"
import { LoginPage } from "./pages/login-page.tsx"
import { LogsPage } from "./pages/logs-page.tsx"
import { RepoDetailPage } from "./pages/repo-detail-page.tsx"
import { ReposPage } from "./pages/repos-page.tsx"
import { SettingsPage } from "./pages/settings-page.tsx"

function RequireAuth() {
  const [state, setState] = useState<"loading" | "in" | "out">("loading")
  useEffect(() => {
    void api("/api/auth/me")
      .then(() => setState("in"))
      .catch(() => setState("out"))
  }, [])
  if (state === "loading") return <p className="p-6 text-sm text-muted-foreground">正在确认登录状态…</p>
  if (state === "out") return <Navigate to="/login" replace />
  return <Layout />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<ReposPage />} />
        <Route path="repos/:id" element={<RepoDetailPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
