"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AdminGate } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { PipelineBoard } from "@/components/admin/pipeline/PipelineBoard";
import { SuggestedTrainersPanel } from "@/components/admin/matching/SuggestedTrainersPanel";
import { EmptyState } from "@/components/ui/EmptyState";

function PipelinePage() {
  const raw = useSearchParams().get("id");
  const id = raw && /^\d+$/.test(raw) ? Number(raw) : null;
  return (
    <main data-testid="admin-pipeline-page" className="mx-auto max-w-6xl px-4 py-8">
      <AdminHeader current="opportunities" />
      <div className="mb-5">
        <Link href="/admin/opportunities/" className="text-sm font-medium text-brand-700 hover:underline">
          ← Opportunities
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-stone-900">Applicants</h1>
      </div>
      {id === null ? (
        <EmptyState icon="🔍" title="No opportunity selected." hint="Open a listing from the Opportunities list." />
      ) : (
        <div className="space-y-8">
          <PipelineBoard opportunityId={id} />
          <SuggestedTrainersPanel opportunityId={id} />
        </div>
      )}
    </main>
  );
}

export default function AdminPipelinePage() {
  return (
    <AdminGate purpose="to review applicants">
      <Suspense fallback={<main className="mx-auto max-w-6xl px-4 py-8" />}>
        <PipelinePage />
      </Suspense>
    </AdminGate>
  );
}
