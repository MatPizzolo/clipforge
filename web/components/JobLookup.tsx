"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isJobId, normalizeJobInput } from "@/lib/jobId";

export function JobLookup() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [invalid, setInvalid] = useState(false);
  return (
    <form
      className="space-y-1"
      onSubmit={(event) => {
        event.preventDefault();
        const id = normalizeJobInput(value);
        if (!isJobId(id)) return setInvalid(true);
        router.push(`/jobs/${id}`);
      }}
    >
      <div className="flex gap-2">
        <Input
          aria-label="Job id"
          placeholder="Open a job id…"
          value={value}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          onChange={(event) => { setValue(event.target.value); setInvalid(false); }}
        />
        <Button type="submit">Go</Button>
      </div>
      {invalid && <p className="text-xs text-destructive">That isn&apos;t a job id (like 20260929-3fa9c1d2-4b7e).</p>}
    </form>
  );
}
