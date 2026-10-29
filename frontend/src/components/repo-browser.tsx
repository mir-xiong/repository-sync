import { useEffect, useState } from "react"
import Markdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import rehypeSanitize from "rehype-sanitize"
import remarkGfm from "remark-gfm"
import { ExternalLink, File, Folder, FolderGit2 } from "lucide-react"
import { toast } from "sonner"
import { api, formatBytes } from "../lib/api.ts"
import { cn } from "../lib/utils.ts"
import { Button } from "./ui/button.tsx"
import { Card } from "./ui/card.tsx"

type Entry = { name: string; path: string; type: string; size: string }
type Preview = {
  path: string
  kind: "text" | "image" | "binary"
  media_type: string
  content: string
  truncated: boolean
  size: number
}

const README_NAMES = ["README.md", "readme.md", "README.markdown", "README.txt", "README"]

export function RepoBrowser({ repoId, branch, upstreamUrl, platform }: { repoId: number; branch: string; upstreamUrl: string; platform: string }) {
  const [dir, setDir] = useState("")
  const [entries, setEntries] = useState<Entry[]>([])
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState("")

  const loadDir = async (next: string) => {
    const tree = await api<{ entries: Entry[] }>(`/api/repos/${repoId}/tree?path=${encodeURIComponent(next)}`)
    setDir(next)
    setEntries(tree.entries)
    setError("")
    return tree.entries
  }

  const openFile = async (path: string) => {
    const data = await api<Preview>(`/api/repos/${repoId}/file?path=${encodeURIComponent(path)}`)
    setPreview(data)
  }

  useEffect(() => {
    void loadDir("")
      .then(async (items) => {
        const readme = README_NAMES.find((name) => items.some((entry) => entry.type === "file" && entry.name === name))
        if (readme) await openFile(readme)
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "无法读取目录"))
  }, [repoId])

  const openEntry = async (entry: Entry) => {
    if (entry.type === "dir") {
      try {
        await loadDir(entry.path)
      } catch (caught) {
        toast.error(caught instanceof Error ? caught.message : "无法打开目录")
      }
      return
    }
    if (entry.type !== "file") {
      toast.error("子模块不能在这里展开")
      return
    }
    try {
      await openFile(entry.path)
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : "无法预览")
    }
  }

  const crumbs = dir ? dir.split("/") : []

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <h2 className="font-semibold">仓库内容</h2>
          <p className="text-sm text-muted-foreground">只读查看默认分支 {branch || "—"}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1 border-b px-3 py-2 text-sm">
        <Crumb label="根目录" active={!dir} onClick={() => void loadDir("").catch((caught: unknown) => toast.error(caught instanceof Error ? caught.message : "无法打开目录"))} />
        {crumbs.map((part, index) => {
          const target = crumbs.slice(0, index + 1).join("/")
          return (
            <span key={target} className="inline-flex items-center gap-1">
              <span className="text-muted-foreground" aria-hidden="true">/</span>
              <Crumb label={part} active={index === crumbs.length - 1} onClick={() => void loadDir(target).catch((caught: unknown) => toast.error(caught instanceof Error ? caught.message : "无法打开目录"))} />
            </span>
          )
        })}
      </div>
      {error ? <p className="px-4 py-6 text-sm text-destructive" role="alert">{error}</p> : (
        <div className="grid lg:grid-cols-[18rem_minmax(0,1fr)]">
          <ul className="border-b p-2 lg:border-r lg:border-b-0">
            {entries.length === 0 ? <li className="px-2 py-6 text-sm text-muted-foreground">这个目录里没有文件。</li> : null}
            {entries.map((entry) => (
              <li key={entry.path}>
                <button
                  type="button"
                  className={cn(
                    "flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-lg px-2 text-left text-sm hover:bg-accent",
                    preview?.path === entry.path && "bg-accent",
                  )}
                  onClick={() => void openEntry(entry)}
                >
                  {entry.type === "dir" ? <Folder className="size-4 shrink-0 text-primary" aria-hidden="true" /> : entry.type === "submodule" ? <FolderGit2 className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : <File className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                  <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                  {entry.size ? <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{formatBytes(Number(entry.size))}</span> : null}
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0 p-4">
            <FileView repoId={repoId} preview={preview} upstreamUrl={upstreamFileUrl(upstreamUrl, platform, branch, preview?.path ?? "")} />
          </div>
        </div>
      )}
    </Card>
  )
}

function Crumb({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={cn("min-h-11 cursor-pointer rounded-md px-2", active ? "font-medium" : "text-muted-foreground hover:text-foreground")} onClick={onClick}>
      {label}
    </button>
  )
}

function FileView({ repoId, preview, upstreamUrl }: { repoId: number; preview: Preview | null; upstreamUrl: string | null }) {
  if (!preview) return <p className="py-8 text-sm text-muted-foreground">从左侧选择一个文件。</p>
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="min-w-0 font-mono text-sm font-medium break-all">{preview.path}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-muted-foreground">
            {formatBytes(preview.size)}
            {preview.truncated ? " · 只显示前 200KB" : ""}
          </p>
          {upstreamUrl ? (
            <Button asChild variant="outline">
              <a href={upstreamUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="size-4" aria-hidden="true" />
                在上游打开
              </a>
            </Button>
          ) : null}
        </div>
      </div>
      {preview.kind === "image" ? (
        <img className="max-h-[28rem] max-w-full rounded-lg border bg-muted object-contain" alt={preview.path} src={`data:${preview.media_type};base64,${preview.content}`} />
      ) : preview.kind === "binary" ? (
        <p className="text-sm text-muted-foreground">这是二进制文件，不能在页面里预览。</p>
      ) : isMarkdown(preview.path) ? (
        <MarkdownBody repoId={repoId} filePath={preview.path} content={preview.content} />
      ) : (
        <pre className="overflow-auto rounded-xl bg-muted p-4 font-mono text-xs leading-5">{preview.content}</pre>
      )}
    </div>
  )
}

function MarkdownBody({ repoId, filePath, content }: { repoId: number; filePath: string; content: string }) {
  return (
    <div className="markdown text-sm leading-6">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeSanitize]}
        components={{
          img: ({ src, alt }) => <RepoImage repoId={repoId} filePath={filePath} src={typeof src === "string" ? src : undefined} alt={alt} />,
        }}
      >
        {content}
      </Markdown>
    </div>
  )
}

function RepoImage({ repoId, filePath, src, alt }: { repoId: number; filePath: string; src?: string; alt?: string }) {
  if (!src) return null
  const local = repoRelativePath(filePath, src)
  const url = local ? `/api/repos/${repoId}/raw?path=${encodeURIComponent(local)}` : src
  return <img className="my-3 max-h-[32rem] max-w-full rounded-lg border bg-muted object-contain" alt={alt ?? ""} src={url} />
}

export function repoRelativePath(filePath: string, src: string): string | null {
  const raw = src.trim()
  if (!raw || raw.startsWith("data:") || raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("//")) return null
  const pathname = raw.split(/[?#]/, 1)[0] ?? ""
  let decoded = pathname
  try {
    decoded = decodeURIComponent(pathname)
  } catch {
    decoded = pathname
  }
  const parts = decoded.startsWith("/") ? [] : filePath.split("/").slice(0, -1)
  for (const part of decoded.split("/")) {
    if (!part || part === ".") continue
    if (part === "..") {
      if (parts.length === 0) return null
      parts.pop()
      continue
    }
    parts.push(part)
  }
  const path = parts.join("/")
  return path || null
}

export function upstreamFileUrl(upstreamUrl: string, platform: string, branch: string, path: string): string | null {
  if ((platform !== "github" && platform !== "gitee") || !upstreamUrl.startsWith("https://") || !branch || !path) return null
  const base = upstreamUrl.replace(/\.git$/i, "").replace(/\/$/, "")
  const ref = branch.split("/").map(encodeURIComponent).join("/")
  const file = path.split("/").map(encodeURIComponent).join("/")
  return `${base}/blob/${ref}/${file}`
}

function isMarkdown(path: string): boolean {
  const name = path.split("/").pop()?.toLowerCase() ?? ""
  return name === "readme" || name.endsWith(".md") || name.endsWith(".markdown")
}
