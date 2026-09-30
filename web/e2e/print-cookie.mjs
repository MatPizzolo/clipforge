// Prints a session cookie value signed with $AUTH_SECRET (use the same value as in .env.local).
// Add it in the browser's dev tools as cookie `authjs.session-token` for localhost.
import { encode } from "next-auth/jwt";

const secret = process.env.AUTH_SECRET;
if (!secret) throw new Error("set AUTH_SECRET (the same value as in .env.local)");
const salt = "authjs.session-token";
console.log(await encode({ token: { name: "Owner", email: "owner@example.com", sub: "1" }, secret, salt }));
