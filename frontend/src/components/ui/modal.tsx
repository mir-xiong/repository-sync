import * as Dialog from "@radix-ui/react-dialog"
import type { ReactNode } from "react"

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-[min(40rem,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border bg-background p-6 text-foreground shadow-xl">
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <div className="mt-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
