import type { Metadata } from "next";
import Link from "next/link";

import { Container, PageHeader } from "@/components/page-shell";
import { buttonVariants } from "@/components/ui/button";
import { notFoundPage } from "@/lib/copy";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: notFoundPage.title };

export default function NotFound() {
  return (
    <Container>
      <PageHeader title={notFoundPage.title} lead={notFoundPage.lead}>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href={routes.events} className={cn(buttonVariants(), "h-10 px-4")}>
            {notFoundPage.cta}
          </Link>
          <Link href={routes.home} className={cn(buttonVariants({ variant: "outline" }), "h-10 px-4")}>
            {notFoundPage.home}
          </Link>
        </div>
      </PageHeader>
    </Container>
  );
}
