"use client"

import { CircleAlertIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

// Fallback for unexpected errors. Expected API failures are rendered by the pages
// themselves (ApiErrorState); production builds hide the message here.
export default function AdminError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="p-4 lg:p-6">
      <Alert variant="destructive">
        <CircleAlertIcon />
        <AlertTitle>Something went wrong</AlertTitle>
        <AlertDescription>
          {error.digest ? `Error ${error.digest}. See the admin server log.` : error.message}
        </AlertDescription>
      </Alert>
      <Button className="mt-4" variant="outline" size="sm" onClick={() => retry()}>
        Try again
      </Button>
    </div>
  )
}
