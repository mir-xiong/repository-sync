import { afterEach } from "vitest"
import { cleanup } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"

afterEach(() => {
  cleanup()
  document.documentElement.className = ""
  document.documentElement.removeAttribute("style")
  document.documentElement.removeAttribute("data-theme")
  document.documentElement.removeAttribute("data-mode")
  document.documentElement.removeAttribute("data-resolved-mode")
  localStorage.clear()
})

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

Element.prototype.scrollIntoView = () => undefined
