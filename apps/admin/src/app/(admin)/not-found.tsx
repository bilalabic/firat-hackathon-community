import Link from "next/link"

export default function NotFound() {
  return (
    <div className="grid gap-2 p-4 lg:p-6">
      <h1 className="text-base font-medium">Not found</h1>
      <p className="text-sm text-muted-foreground">This record does not exist or was removed.</p>
      <Link href="/" className="text-sm underline-offset-4 hover:underline">
        Back to Overview
      </Link>
    </div>
  )
}
