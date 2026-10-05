import Link from "next/link";

import { footer, nav, site } from "@/lib/copy";
import { externalLinks, routes } from "@/lib/routes";

import { ExternalLink } from "./external-link";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t">
      <div className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-10 text-sm text-muted-foreground sm:grid-cols-[1fr_auto] sm:px-6">
        <div className="max-w-prose space-y-2">
          <p className="font-medium text-foreground">{site.name}</p>
          <p>{footer.line}</p>
          <p>{footer.sources}</p>
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-2 sm:flex-col sm:items-end">
          <li>
            <Link className="hover:text-foreground" href={routes.events}>
              {nav.events}
            </Link>
          </li>
          <li>
            <Link className="hover:text-foreground" href={routes.community}>
              {nav.community}
            </Link>
          </li>
          <li>
            <Link className="hover:text-foreground" href={routes.contribute}>
              {nav.contribute}
            </Link>
          </li>
          <li>
            <Link className="hover:text-foreground" href={routes.about}>
              {nav.about}
            </Link>
          </li>
          <li>
            <ExternalLink className="hover:text-foreground" href={externalLinks.github}>
              {footer.github}
            </ExternalLink>
          </li>
        </ul>
      </div>
    </footer>
  );
}
