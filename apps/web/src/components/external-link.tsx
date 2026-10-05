import type { ComponentProps } from "react";

import { common } from "@/lib/copy";

/** Link to another site: new tab, no opener/referrer, announced to screen readers. */
export function ExternalLink({ children, ...props }: ComponentProps<"a"> & { href: string }) {
  return (
    <a target="_blank" rel="noopener noreferrer" {...props}>
      {children}
      <span className="sr-only"> {common.opensInNewTab}</span>
    </a>
  );
}
