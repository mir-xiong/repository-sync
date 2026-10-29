import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { ThemeContext } from "./theme-context.ts"
import { themePresets } from "../lib/theme-catalog.generated.ts"
import {
  applyThemeToRoot,
  normalizeMode,
  normalizeThemeId,
  readStoredPreference,
  resolveThemeMode,
  systemPrefersDark,
  writeStoredPreference,
} from "../lib/theme-runtime.ts"
import type { ThemeMode, ThemePreference } from "../lib/theme-types.ts"

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(() => readStoredPreference())
  const [systemDark, setSystemDark] = useState(() => systemPrefersDark())
  const preferenceRef = useRef(preference)
  preferenceRef.current = preference

  const commit = (next: ThemePreference) => {
    const normalized = { themeId: normalizeThemeId(next.themeId), mode: normalizeMode(next.mode) }
    preferenceRef.current = normalized
    setPreference(normalized)
    writeStoredPreference(normalized)
    applyThemeToRoot(document.documentElement, normalized, resolveThemeMode(normalized.mode, systemPrefersDark()))
  }

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const apply = () => {
      setSystemDark(media.matches)
      const current = preferenceRef.current
      applyThemeToRoot(document.documentElement, current, resolveThemeMode(current.mode, media.matches))
    }
    apply()
    media.addEventListener("change", apply)
    return () => media.removeEventListener("change", apply)
  }, [])

  const value = useMemo(() => {
    const resolvedMode = resolveThemeMode(preference.mode, systemDark)
    return {
      themeId: preference.themeId,
      mode: preference.mode,
      resolvedMode,
      setTheme: (themeId: string) => commit({ ...preferenceRef.current, themeId }),
      setMode: (mode: ThemeMode) => commit({ ...preferenceRef.current, mode }),
      randomTheme: () => {
        const candidates = themePresets.map((item) => item.id).filter((id) => id !== preferenceRef.current.themeId)
        const next = candidates[Math.floor(Math.random() * candidates.length)] ?? preferenceRef.current.themeId
        commit({ ...preferenceRef.current, themeId: next })
      },
    }
  }, [preference, systemDark])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
