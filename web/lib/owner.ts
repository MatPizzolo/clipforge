import { z } from "zod";

// One allow-listed owner (spec §4): the GitHub account's primary, verified email must equal
// OWNER_EMAIL. The editable profile email isn't trusted. Unset OWNER_EMAIL refuses everyone.
export type GitHubEmail = { email: string; primary: boolean; verified: boolean };

const zEmails = z.array(z.object({ email: z.string(), primary: z.boolean(), verified: z.boolean() }));

export function isOwner(emails: GitHubEmail[], owner: string | undefined): boolean {
  const want = owner?.trim().toLowerCase();
  if (!want) return false;
  return emails.some((e) => e.primary && e.verified && e.email.trim().toLowerCase() === want);
}

export async function fetchGitHubEmails(accessToken: string, fetchImpl: typeof fetch = fetch): Promise<GitHubEmail[]> {
  try {
    const res = await fetchImpl("https://api.github.com/user/emails", {
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "clipforge-dashboard",
      },
      cache: "no-store",
    });
    if (!res.ok) return [];
    const parsed = zEmails.safeParse(await res.json());
    return parsed.success ? parsed.data.map(({ email, primary, verified }) => ({ email, primary, verified })) : [];
  } catch {
    return [];
  }
}
