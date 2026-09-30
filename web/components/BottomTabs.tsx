"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isActive } from "@/components/nav";
import { cn } from "@/lib/utils";

// Phone only: at ≥ 1024 px the sidebar replaces it.
const TABS = [
  { href: "/", label: "Home" },
  { href: "/jobs", label: "Jobs" },
  { href: "/more", label: "More" },
];

export function BottomTabs() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Tabs"
      className="fixed inset-x-0 bottom-0 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      <ul className="mx-auto flex max-w-md">
        {TABS.map((tab) => (
          <li key={tab.href} className="flex-1">
            <Link
              href={tab.href}
              aria-current={isActive(tab.href, pathname) ? "page" : undefined}
              className={cn(
                "block py-3 text-center text-sm",
                isActive(tab.href, pathname) ? "font-semibold text-foreground" : "text-muted-foreground",
              )}
            >
              {tab.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
