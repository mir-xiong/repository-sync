import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"
import { ThemePresetSelector } from "./theme-preset-selector.tsx"
import { ThemeProvider } from "./theme-provider.tsx"

describe("theme selector", () => {
  it("searches, selects a preset, and keeps light dark system separate", async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <ThemePresetSelector />
      </ThemeProvider>,
    )
    await user.click(screen.getByRole("button", { name: "切换主题" }))
    await user.type(screen.getByRole("textbox", { name: "搜索主题" }), "vercel")
    expect(screen.getByText("1 个主题")).toBeInTheDocument()
    await user.click(screen.getByRole("option", { name: /Vercel/ }))
    expect(document.documentElement.dataset.theme).toBe("vercel")
    expect(JSON.parse(localStorage.getItem("repository-sync.theme") ?? "{}").themeId).toBe("vercel")
    await user.click(screen.getByRole("button", { name: "切换主题" }))
    await user.click(screen.getByRole("button", { name: "深色" }))
    expect(document.documentElement.dataset.mode).toBe("dark")
    expect(document.documentElement.dataset.resolvedMode).toBe("dark")
    expect(JSON.parse(localStorage.getItem("repository-sync.theme") ?? "{}").mode).toBe("dark")
  })
})
