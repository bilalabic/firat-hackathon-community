"use client";

import { Container, PageHeader } from "@/components/page-shell";
import { Button } from "@/components/ui/button";
import { errorPage } from "@/lib/copy";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <Container>
      <PageHeader title={errorPage.title} lead={errorPage.lead}>
        <Button type="button" onClick={() => retry()} className="h-10 px-4">
          {errorPage.retry}
        </Button>
      </PageHeader>
    </Container>
  );
}
