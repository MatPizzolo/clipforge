import { JobLookup } from "@/components/JobLookup";
import { RecentJobs } from "@/components/job/RecentJobs";

export default function JobsPage() {
  return (
    <div className="space-y-3 lg:space-y-4">
      <div className="lg:max-w-lg"><JobLookup /></div>
      <RecentJobs />
    </div>
  );
}
