"use client"

import { useTransition } from "react"
import { useRouter } from "next/navigation"
import { RefreshCwIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

/** Re-renders the current page on the server, which runs its checks again. */
export function RerunButton() {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() => startTransition(() => router.refresh())}
    >
      <RefreshCwIcon data-icon="inline-start" className={pending ? "animate-spin" : undefined} />
      {pending ? "Running…" : "Run checks again"}
    </Button>
  )
}
