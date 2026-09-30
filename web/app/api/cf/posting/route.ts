import { hasSession } from "@/lib/session";
import { getPosting, toResponse } from "@/lib/upstream";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  if (!(await hasSession())) return Response.json({ error: "unauthorized" }, { status: 401 });
  return toResponse(await getPosting());
}
