import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { Toaster } from "sonner"
import App from "./App.tsx"
import { ThemeProvider } from "./components/theme-provider.tsx"
import { bootstrapTheme } from "./lib/theme-runtime.ts"
import "./index.css"

bootstrapTheme(document)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <App />
        <Toaster position="top-center" />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
