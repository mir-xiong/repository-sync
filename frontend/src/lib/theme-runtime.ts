import { themePresets } from "./theme-catalog.generated.ts"
import {
  COLOR_TOKENS,
  CSS_VARIABLE_NAMES,
  DEFAULT_THEME_ID,
  FONT_TOKENS,
  LENGTH_TOKENS,
  LETTER_TOKENS,
  OPACITY_TOKENS,
  THEME_STORAGE_KEY,
  type ResolvedThemeMode,
  type ThemeMode,
  type ThemePreference,
  type ThemePreset,
} from "./theme-types.ts"

const SAFE_COLOR: Record<string, string> = {
  background: "#ffffff",
  foreground: "#171717",
  card: "#ffffff",
  "card-foreground": "#171717",
  popover: "#ffffff",
  "popover-foreground": "#171717",
  primary: "#2563eb",
  "primary-foreground": "#ffffff",
  secondary: "#f3f4f6",
  "secondary-foreground": "#374151",
  muted: "#f3f4f6",
  "muted-foreground": "#6b7280",
  accent: "#e0f2fe",
  "accent-foreground": "#1e3a8a",
  destructive: "#dc2626",
  "destructive-foreground": "#ffffff",
  border: "#e5e7eb",
  input: "#e5e7eb",
  ring: "#2563eb",
  "chart-1": "#2563eb",
  "chart-2": "#16a34a",
  "chart-3": "#d97706",
  "chart-4": "#7c3aed",
  "chart-5": "#db2777",
  sidebar: "#f9fafb",
  "sidebar-foreground": "#171717",
  "sidebar-primary": "#2563eb",
  "sidebar-primary-foreground": "#ffffff",
  "sidebar-accent": "#e0f2fe",
  "sidebar-accent-foreground": "#1e3a8a",
  "sidebar-border": "#e5e7eb",
  "sidebar-ring": "#2563eb",
  "shadow-color": "#000000",
}

const SAFE_LENGTH: Record<string, string> = {
  radius: "0.5rem",
  "shadow-blur": "3px",
  "shadow-spread": "0px",
  "shadow-offset-x": "0px",
  "shadow-offset-y": "1px",
  spacing: "0.25rem",
}

const SAFE_FONT: Record<string, string> = {
  "font-sans": "ui-sans-serif, system-ui, sans-serif",
  "font-serif": "ui-serif, Georgia, serif",
  "font-mono": "ui-monospace, monospace",
}

const ALIASES: Record<string, string> = {}
const byId = new Map(themePresets.map((preset) => [preset.id, preset]))

export function normalizeThemeId(id: unknown): string {
  const raw = typeof id === "string" ? id : ""
  const aliased = ALIASES[raw] ?? raw
  return byId.has(aliased) ? aliased : DEFAULT_THEME_ID
}

export function normalizeMode(mode: unknown): ThemeMode {
  return mode === "light" || mode === "dark" || mode === "system" ? mode : "system"
}

export function getPreset(id: string): ThemePreset {
  return byId.get(normalizeThemeId(id)) ?? themePresets[0]
}

export function isColor(value: string): boolean {
  const text = value.trim()
  if (!text || /[;{}<>]/.test(text)) return false
  if (/^(inherit|initial|revert|revert-layer|unset)$/i.test(text)) return false
  if (/url\s*\(|var\s*\(/i.test(text)) return false
  if (text === "transparent" || /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(text)) return true
  if (!/^(rgb|rgba|hsl|hsla|oklch|oklab|lab|lch|color|color-mix)\(/i.test(text) || !text.endsWith(")")) return false
  if (!/\d/.test(text)) return false
  return !/\b(not-a-color|undefined|null|expression)\b/i.test(text)
}

export function isLength(value: string): boolean {
  const text = value.trim()
  return text === "0" || /^-?(?:0|\d+(?:\.\d+)?)(?:px|rem|em|%)$/.test(text)
}

export function isFont(value: string): boolean {
  const text = value.trim()
  return Boolean(text) && !/[;{}<>]/.test(text) && !/url\s*\(|var\s*\(/i.test(text)
}

export function isOpacity(value: string): boolean {
  const text = value.trim()
  if (text.endsWith("%")) {
    const amount = Number(text.slice(0, -1))
    return Number.isFinite(amount) && amount >= 0 && amount <= 100
  }
  const amount = Number(text)
  return Number.isFinite(amount) && amount >= 0 && amount <= 1
}

export function isLetterSpacing(value: string): boolean {
  return value.trim() === "normal" || isLength(value)
}

function firstValid(values: Array<string | undefined>, accept: (value: string) => boolean, fallback: string): string {
  for (const value of values) {
    if (value && accept(value)) return value
  }
  return fallback
}

export function resolveTokens(preset: ThemePreset, mode: ResolvedThemeMode): Record<string, string> {
  const fallback = getPreset(DEFAULT_THEME_ID)
  const other: ResolvedThemeMode = mode === "light" ? "dark" : "light"
  const tokens: Record<string, string> = {}
  for (const token of COLOR_TOKENS) {
    tokens[token] = firstValid(
      [preset.styles[mode][token], fallback.styles[mode][token]],
      isColor,
      SAFE_COLOR[token],
    )
  }
  for (const token of LENGTH_TOKENS) {
    tokens[token] = firstValid(
      [preset.styles[mode][token], preset.styles[other][token], fallback.styles[mode][token]],
      isLength,
      SAFE_LENGTH[token],
    )
  }
  for (const token of FONT_TOKENS) {
    tokens[token] = firstValid(
      [preset.styles[mode][token], preset.styles[other][token], fallback.styles[mode][token]],
      isFont,
      SAFE_FONT[token],
    )
  }
  for (const token of OPACITY_TOKENS) {
    tokens[token] = firstValid(
      [preset.styles[mode][token], preset.styles[other][token], fallback.styles[mode][token]],
      isOpacity,
      "0.08",
    )
  }
  for (const token of LETTER_TOKENS) {
    tokens[token] = firstValid(
      [preset.styles[mode][token], preset.styles[other][token], fallback.styles[mode][token]],
      isLetterSpacing,
      "0em",
    )
  }
  return tokens
}

export function opacityRatio(value: string): number {
  if (value.trim().endsWith("%")) return Number(value.trim().slice(0, -1)) / 100
  return Number(value)
}

export function buildShadow(tokens: Record<string, string>): string {
  const color = tokens["shadow-color"] || SAFE_COLOR["shadow-color"]
  const ratio = opacityRatio(tokens["shadow-opacity"] || "0.08")
  const percent = Math.round(Math.min(1, Math.max(0, ratio)) * 100)
  const x = tokens["shadow-offset-x"] || "0px"
  const y = tokens["shadow-offset-y"] || "1px"
  const blur = tokens["shadow-blur"] || "3px"
  const spread = tokens["shadow-spread"] || "0px"
  return `${x} ${y} ${blur} ${spread} color-mix(in srgb, ${color} ${percent}%, transparent)`
}

export function resolveThemeMode(mode: ThemeMode, prefersDark: boolean): ResolvedThemeMode {
  if (mode === "system") return prefersDark ? "dark" : "light"
  return mode
}

export function systemPrefersDark(win: Window | undefined = typeof window === "undefined" ? undefined : window): boolean {
  try {
    return Boolean(win?.matchMedia?.("(prefers-color-scheme: dark)").matches)
  } catch {
    return false
  }
}

export function readStoredPreference(storage: Storage | null = safeStorage()): ThemePreference {
  const fallback = { themeId: DEFAULT_THEME_ID, mode: "system" as const }
  if (!storage) return fallback
  try {
    const raw = storage.getItem(THEME_STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as { version?: unknown; themeId?: unknown; mode?: unknown }
    if (parsed.version !== 1) return fallback
    return { themeId: normalizeThemeId(parsed.themeId), mode: normalizeMode(parsed.mode) }
  } catch {
    return fallback
  }
}

export function writeStoredPreference(preference: ThemePreference, storage: Storage | null = safeStorage()): void {
  if (!storage) return
  try {
    storage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        themeId: normalizeThemeId(preference.themeId),
        mode: normalizeMode(preference.mode),
      }),
    )
  } catch {
    // 存储不可用时保留当前内存主题。
  }
}

export function applyThemeToRoot(root: HTMLElement, preference: ThemePreference, resolved: ResolvedThemeMode): void {
  const preset = getPreset(preference.themeId)
  const tokens = resolveTokens(preset, resolved)
  const shadow = buildShadow(tokens)
  root.dataset.theme = preset.id
  root.dataset.mode = normalizeMode(preference.mode)
  root.dataset.resolvedMode = resolved
  root.classList.toggle("dark", resolved === "dark")
  root.style.colorScheme = resolved
  for (const [key, value] of Object.entries(tokens)) {
    if (CSS_VARIABLE_NAMES.has(key)) root.style.setProperty(`--${key}`, value)
  }
  for (const name of ["shadow", "shadow-sm", "shadow-md", "shadow-lg"]) {
    root.style.setProperty(`--${name}`, shadow)
  }
  root.style.fontFamily = tokens["font-sans"]
}

export function bootstrapTheme(doc: Document = document): ThemePreference {
  const preference = readStoredPreference()
  const resolved = resolveThemeMode(preference.mode, systemPrefersDark(doc.defaultView ?? undefined))
  applyThemeToRoot(doc.documentElement, preference, resolved)
  return preference
}

function safeStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function swatches(preset: ThemePreset): string[] {
  const styles = preset.styles.light
  return ["primary", "secondary", "accent", "background"].map((token) =>
    styles[token] && isColor(styles[token]) ? styles[token] : SAFE_COLOR[token],
  )
}
