import { hasSession } from "@/lib/session";
import { getJob, toResponse } from "@/lib/upstream";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }): Promise<Response> {
  if (!(await hasSession())) return Response.json({ error: "unauthorized" }, { status: 401 });
  const { id } = await params;
  return toResponse(await getJob(id));
}
