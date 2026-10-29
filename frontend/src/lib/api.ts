export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function messageFrom(data: unknown): string {
  if (!data || typeof data !== "object" || !("detail" in data)) return "请求失败"
  const detail = (data as { detail: unknown }).detail
  if (typeof detail === "string") return detail
  return "请检查输入"
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  const response = await fetch(path, { ...init, headers, credentials: "include" })
  const text = await response.text()
  const data = text ? (JSON.parse(text) as unknown) : null
  if (!response.ok) throw new ApiError(response.status, messageFrom(data))
  return data as T
}

export function formatTime(value: string | null): string {
  if (!value) return "—"
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value))
}

export function formatBytes(value: number): string {
  if (!value) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}
