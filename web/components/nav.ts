// The dashboard's pages (08 §2), in sidebar order. Unbuilt ones render disabled ("coming in S3");
// on the phone they're listed under More.
export type NavItem = { href: string; label: string; built: boolean };

export const NAV: NavItem[] = [
  { href: "/", label: "Home", built: true },
  { href: "/jobs", label: "Jobs", built: true },
  { href: "/review", label: "Review", built: false },
  { href: "/calendar", label: "Calendar", built: false },
  { href: "/accounts", label: "Accounts", built: false },
  { href: "/sources", label: "Sources", built: false },
  { href: "/produce", label: "Produce", built: false },
  { href: "/costs", label: "Costs", built: false },
];

export const COMING_SOON = "coming in S3";

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
