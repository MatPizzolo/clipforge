import type { ReactNode } from "react";
import { signOut } from "@/auth";
import { BottomTabs } from "@/components/BottomTabs";
import { Providers } from "@/components/Providers";
import { SidebarNav } from "@/components/SidebarNav";
import { isAuthBypassed } from "@/lib/authMode";

// Read AUTH_DISABLED per request, not at build time.
export const dynamic = "force-dynamic";

function SignOut() {
  return (
    <form action={async () => { "use server"; await signOut({ redirectTo: "/login" }); }}>
      <button type="submit" className="text-sm text-muted-foreground">Sign out</button>
    </form>
  );
}

// Phone (< 1024 px): header, one column, bottom tabs. Laptop (≥ 1024 px): sidebar, wide content.
export default function AppLayout({ children }: { children: ReactNode }) {
  const authOff = isAuthBypassed(process.env);
  return (
    <Providers>
      <nav
        aria-label="Sidebar"
        className="fixed inset-y-0 left-0 hidden w-56 flex-col gap-6 border-r bg-background px-3 py-6 lg:flex"
      >
        <span className="px-3 text-lg font-bold">ClipForge</span>
        <SidebarNav />
        {!authOff && <div className="mt-auto px-3"><SignOut /></div>}
      </nav>
      <div className="lg:pl-56">
        {authOff && (
          <p role="status" className="bg-amber-500/15 px-4 py-1 text-center text-xs text-amber-700 dark:text-amber-300">
            Login is off (AUTH_DISABLED): test use only
          </p>
        )}
        <header className="mx-auto flex max-w-md items-center justify-between px-4 pb-2 pt-[max(1rem,env(safe-area-inset-top))] lg:hidden">
          <span className="text-lg font-bold">ClipForge</span>
          {!authOff && <SignOut />}
        </header>
        <main className="mx-auto max-w-md space-y-3 px-3 pb-24 lg:max-w-6xl lg:px-8 lg:pb-10 lg:pt-8">{children}</main>
      </div>
      <BottomTabs />
    </Providers>
  );
}
