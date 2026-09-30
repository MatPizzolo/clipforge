import { redirect } from "next/navigation";
import { JobDetail } from "@/components/job/JobDetail";
import { canonicalJobId } from "@/lib/jobId";

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value; // a malformed %-sequence is just an unknown job
  }
}

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Links with uppercase hex or spaces open the same job, like the lookup box.
  const canonical = canonicalJobId(safeDecode(id));
  if (canonical) redirect(`/jobs/${canonical}`);
  return <JobDetail id={id} />;
}
