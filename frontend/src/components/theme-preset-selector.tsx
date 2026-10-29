import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react"
import { Check, Dices, Monitor, Moon, Palette, Sun } from "lucide-react"
import { themePresets } from "../lib/theme-catalog.generated.ts"
import { swatches } from "../lib/theme-runtime.ts"
import type { ThemeMode } from "../lib/theme-types.ts"
import { cn } from "../lib/utils.ts"
import { useTheme } from "./theme-context.ts"

const modes: Array<{ id: ThemeMode; label: string; icon: typeof Sun }> = [
  { id: "light", label: "浅色", icon: Sun },
  { id: "dark", label: "深色", icon: Moon },
  { id: "system", label: "跟随系统", icon: Monitor },
]

export function ThemePresetSelector({ placement = "bottom-end" }: { placement?: "bottom-end" | "top-start" }) {
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const [narrow, setNarrow] = useState(() => window.matchMedia("(max-width: 767px)").matches)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const current = themePresets.find((item) => item.id === theme.themeId) ?? themePresets[0]
  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) return themePresets
    return themePresets.filter((item) => item.label.toLowerCase().includes(keyword) || item.id.includes(keyword))
  }, [query])

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)")
    const onChange = () => setNarrow(media.matches)
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [])

  useEffect(() => {
    setActive(0)
  }, [query, open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault()
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [open])

  useEffect(() => {
    const node = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)
    node?.scrollIntoView?.({ block: "nearest" })
  }, [active, open])

  const choose = (id: string) => {
    theme.setTheme(id)
    setOpen(false)
    buttonRef.current?.focus()
  }

  const onListKey = (event: ReactKeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActive((index) => Math.min(filtered.length - 1, index + 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive((index) => Math.max(0, index - 1))
    } else if (event.key === "Enter" && filtered[active]) {
      event.preventDefault()
      choose(filtered[active].id)
    }
  }

  const panel = (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{filtered.length} 个主题</p>
        <button type="button" className="inline-flex min-h-11 items-center gap-1 rounded-md border px-3 text-sm" onClick={theme.randomTheme}>
          <Dices className="size-4" aria-hidden="true" />
          随机
        </button>
      </div>
      <div className="grid grid-cols-3 gap-2" role="group" aria-label="显示模式">
        {modes.map((mode) => {
          const Icon = mode.icon
          const selected = theme.mode === mode.id
          return (
            <button
              key={mode.id}
              type="button"
              aria-pressed={selected}
              className={cn("inline-flex min-h-11 items-center justify-center gap-1 rounded-md border text-sm", selected && "border-primary bg-accent text-accent-foreground")}
              onClick={() => theme.setMode(mode.id)}
            >
              <Icon className="size-4" aria-hidden="true" />
              {mode.label}
            </button>
          )
        })}
      </div>
      <input
        aria-label="搜索主题"
        aria-controls={listId}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={onListKey}
        placeholder="搜索名称或 ID"
        className="h-11 rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div
        id={listId}
        ref={listRef}
        role="listbox"
        aria-label="主题列表"
        aria-activedescendant={filtered[active] ? `${listId}-${filtered[active].id}` : undefined}
        tabIndex={0}
        onKeyDown={onListKey}
        className="max-h-80 space-y-1 overflow-auto"
      >
        {filtered.length === 0 ? <p className="px-2 py-6 text-center text-sm text-muted-foreground">没有匹配的主题</p> : null}
        {filtered.map((preset, index) => {
          const selected = preset.id === theme.themeId
          return (
            <button
              key={preset.id}
              id={`${listId}-${preset.id}`}
              type="button"
              role="option"
              aria-selected={selected}
              data-index={index}
              className={cn("flex min-h-11 w-full items-center gap-3 rounded-md px-2 text-left hover:bg-accent", index === active && "bg-accent")}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(preset.id)}
            >
              <span className="flex gap-1" aria-hidden="true">
                {swatches(preset).map((color, swatchIndex) => (
                  <span key={`${preset.id}-${swatchIndex}`} className="size-4 rounded-full border" style={{ background: color }} />
                ))}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{preset.label}</span>
                <span className="block truncate text-xs text-muted-foreground">{preset.id}</span>
              </span>
              {selected ? <Check className="size-4" aria-hidden="true" /> : null}
              {selected ? <span className="sr-only">当前</span> : null}
            </button>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        className="inline-flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-lg border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="切换主题"
        onClick={() => setOpen((value) => !value)}
      >
        <Palette className="size-4" aria-hidden="true" />
        <span className="max-w-32 truncate">{current.label}</span>
      </button>
      {open && !narrow ? (
        <div
          className={
            placement === "top-start"
              ? "absolute bottom-full left-0 z-50 mb-2 w-[22rem] rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg"
              : "absolute right-0 z-50 mt-2 w-[22rem] rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg"
          }
        >
          {panel}
        </div>
      ) : null}
      {open && narrow ? (
        <div className="fixed inset-0 z-50 flex items-end bg-black/40" onClick={() => setOpen(false)}>
          <div
            role="dialog"
            aria-label="切换主题"
            className="max-h-[85dvh] w-full overflow-auto rounded-t-xl border bg-popover p-4 pb-[max(1rem,env(safe-area-inset-bottom))] text-popover-foreground"
            onClick={(event) => event.stopPropagation()}
          >
            {panel}
          </div>
        </div>
      ) : null}
    </div>
  )
}
