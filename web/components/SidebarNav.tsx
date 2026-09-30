"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { COMING_SOON, isActive, NAV } from "@/components/nav";
import { cn } from "@/lib/utils";

export function SidebarNav() {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {NAV.map((item) => (
        <li key={item.href}>
          {item.built ? (
            <Link
              href={item.href}
              aria-current={isActive(item.href, pathname) ? "page" : undefined}
              className={cn(
                "block rounded-md px-3 py-2 text-sm",
                isActive(item.href, pathname) ? "bg-muted font-semibold text-foreground" : "text-muted-foreground hover:bg-muted/60",
              )}
            >
              {item.label}
            </Link>
          ) : (
            <span aria-disabled="true" className="block cursor-not-allowed px-3 py-1.5 text-sm text-muted-foreground/60">
              {item.label}
              <span className="block text-[11px]">{COMING_SOON}</span>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
