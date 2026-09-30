import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";
import { fetchGitHubEmails, isOwner } from "@/lib/owner";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [GitHub],
  session: { strategy: "jwt", maxAge: 7 * 24 * 3600 }, // 7 days; rotating AUTH_SECRET logs everyone out
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ account }) {
      if (account?.provider !== "github" || !account.access_token) return false;
      return isOwner(await fetchGitHubEmails(account.access_token), process.env.OWNER_EMAIL);
    },
  },
});
