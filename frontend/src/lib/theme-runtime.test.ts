import { describe, expect, it } from "vitest"
import { themePresets } from "./theme-catalog.generated.ts"
import {
  applyThemeToRoot,
  buildShadow,
  isColor,
  readStoredPreference,
  resolveTokens,
  writeStoredPreference,
} from "./theme-runtime.ts"
import type { ThemePreset } from "./theme-types.ts"

describe("theme catalog", () => {
  it("has unique ids and both color modes", () => {
    const ids = themePresets.map((preset) => preset.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids).toContain("modern-minimal")
    for (const preset of themePresets) {
      expect(Object.keys(preset.styles.light).length).toBeGreaterThan(0)
      expect(Object.keys(preset.styles.dark).length).toBeGreaterThan(0)
    }
  })
})

describe("theme runtime", () => {
  it("does not fall back a color across modes", () => {
    const preset: ThemePreset = {
      id: "broken",
      label: "Broken",
      source: "PROJECT",
      sourceCommit: null,
      styles: {
        light: { background: "red; background: url(evil)" },
        dark: { background: "#111111" },
      },
    }
    expect(resolveTokens(preset, "light").background.toLowerCase()).toBe("#ffffff")
    expect(resolveTokens(preset, "dark").background.toLowerCase()).toBe("#111111")
  })

  it("rejects invalid colors and builds a shadow with opacity", () => {
    expect(isColor("rgb(not-a-color)")).toBe(false)
    expect(isColor("#112233")).toBe(true)
    expect(buildShadow({
      "shadow-color": "#112233",
      "shadow-opacity": "0.25",
      "shadow-offset-x": "1px",
      "shadow-offset-y": "2px",
      "shadow-blur": "3px",
      "shadow-spread": "4px",
    })).toBe("1px 2px 3px 4px color-mix(in srgb, #112233 25%, transparent)")
  })

  it("falls back when storage is damaged or unavailable", () => {
    const broken = {
      getItem: () => "{",
      setItem: () => undefined,
      removeItem: () => undefined,
      clear: () => undefined,
      key: () => null,
      length: 0,
    } as Storage
    expect(readStoredPreference(broken)).toEqual({ themeId: "modern-minimal", mode: "system" })
    const throwing = {
      getItem: () => {
        throw new Error("blocked")
      },
      setItem: () => {
        throw new Error("blocked")
      },
      removeItem: () => undefined,
      clear: () => undefined,
      key: () => null,
      length: 0,
    } as Storage
    expect(readStoredPreference(throwing).mode).toBe("system")
    expect(() => writeStoredPreference({ themeId: "nope", mode: "dark" }, throwing)).not.toThrow()
  })

  it("applies theme id, mode and variables before render", () => {
    applyThemeToRoot(document.documentElement, { themeId: "unknown-theme", mode: "dark" }, "dark")
    expect(document.documentElement.dataset.theme).toBe("modern-minimal")
    expect(document.documentElement.dataset.mode).toBe("dark")
    expect(document.documentElement.dataset.resolvedMode).toBe("dark")
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe("dark")
    expect(document.documentElement.style.getPropertyValue("--background").toLowerCase()).toBe("#171717")
    expect(document.documentElement.style.getPropertyValue("--shadow")).toContain("color-mix")
  })
})
