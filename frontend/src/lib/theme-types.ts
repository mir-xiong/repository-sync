export type ThemeMode = "light" | "dark" | "system"
export type ResolvedThemeMode = "light" | "dark"

export type ThemePreference = {
  themeId: string
  mode: ThemeMode
}

export type ThemePreset = {
  id: string
  label: string
  source: "TWEAKCN" | "PROJECT"
  sourceCommit: string | null
  styles: {
    light: Record<string, string>
    dark: Record<string, string>
  }
}

export const DEFAULT_THEME_ID = "modern-minimal"
export const THEME_STORAGE_KEY = "repository-sync.theme"

export const COLOR_TOKENS = [
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "destructive",
  "destructive-foreground",
  "border",
  "input",
  "ring",
  "chart-1",
  "chart-2",
  "chart-3",
  "chart-4",
  "chart-5",
  "sidebar",
  "sidebar-foreground",
  "sidebar-primary",
  "sidebar-primary-foreground",
  "sidebar-accent",
  "sidebar-accent-foreground",
  "sidebar-border",
  "sidebar-ring",
  "shadow-color",
] as const

export const LENGTH_TOKENS = [
  "radius",
  "shadow-blur",
  "shadow-spread",
  "shadow-offset-x",
  "shadow-offset-y",
  "spacing",
] as const

export const FONT_TOKENS = ["font-sans", "font-serif", "font-mono"] as const
export const OPACITY_TOKENS = ["shadow-opacity"] as const
export const LETTER_TOKENS = ["letter-spacing"] as const

export const CSS_VARIABLE_NAMES = new Set<string>([
  ...COLOR_TOKENS,
  ...LENGTH_TOKENS,
  ...FONT_TOKENS,
  ...OPACITY_TOKENS,
  ...LETTER_TOKENS,
  "shadow",
  "shadow-sm",
  "shadow-md",
  "shadow-lg",
])
