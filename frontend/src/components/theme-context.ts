import { createContext, useContext } from "react"
import type { ThemeMode } from "../lib/theme-types.ts"

export type ThemeContextValue = {
  themeId: string
  mode: ThemeMode
  resolvedMode: "light" | "dark"
  setTheme: (themeId: string) => void
  setMode: (mode: ThemeMode) => void
  randomTheme: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error("ThemeProvider 缺失")
  return value
}
