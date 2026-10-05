import Link from "next/link";

import { nav, site } from "@/lib/copy";
import { routes } from "@/lib/routes";

import { NavLinks } from "./nav-links";

export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link
          href={routes.home}
          className="flex items-center gap-2 rounded-sm py-1 text-[15px] font-semibold tracking-tight"
        >
          <span aria-hidden="true" className="size-2.5 rounded-full bg-brand" />
          {site.name}
        </Link>
        <nav aria-label={nav.label} className="-mx-2 w-full sm:mx-0 sm:w-auto">
          <NavLinks
            items={[
              { href: routes.events, label: nav.events },
              { href: routes.community, label: nav.community },
              { href: routes.contribute, label: nav.contribute },
              { href: routes.about, label: nav.about },
            ]}
          />
        </nav>
      </div>
    </header>
  );
}
