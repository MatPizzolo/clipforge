import { redirect } from "next/navigation";
import { signIn } from "@/auth";
import { isAuthBypassed } from "@/lib/authMode";
import { safeCallback } from "@/lib/callback";
import { Button } from "@/components/ui/button";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; callbackUrl?: string | string[] }>;
}) {
  const { error, callbackUrl } = await searchParams;
  // Only relative paths come back (lib/callback.ts); anything else returns to Home.
  const returnTo = safeCallback(callbackUrl);
  if (isAuthBypassed(process.env)) redirect(returnTo);
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-4 px-6">
      <h1 className="text-2xl font-bold">ClipForge</h1>
      {error && (
        <p className="text-sm text-destructive">
          {error === "AccessDenied" ? "This GitHub account isn't allowed." : "Sign-in failed. Try again."}
        </p>
      )}
      <form action={async () => { "use server"; await signIn("github", { redirectTo: returnTo }); }}>
        <Button type="submit" className="w-full">Sign in with GitHub</Button>
      </form>
    </main>
  );
}
