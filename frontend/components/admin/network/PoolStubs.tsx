import { StubCard } from "@/components/ui/StubBadge";

/** Phase-12 surfaces on the pool page, rendered as labelled, non-interactive stubs. */
export function MatchingFiltersStub() {
  return (
    <StubCard
      title="Matching filters — level, budget, availability, location"
      description="Rule-based filters to narrow the pool for a listing arrive with matching in Phase 12."
    />
  );
}

export function SuggestedTrainersStub() {
  return (
    <StubCard
      title="Suggested trainers for a listing"
      description="Pick a listing and get a ranked shortlist with reasons — coming in Phase 12."
    />
  );
}
