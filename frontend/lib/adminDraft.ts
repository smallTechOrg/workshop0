/** Admin paste-to-fill drafting client — stub (F6 fills). spec/api.md §Phase 11b. */

import type { CompensationUnit, Currency } from "@/lib/compensation";

export type DraftedField =
  | "title"
  | "type"
  | "summary"
  | "description_md"
  | "topics"
  | "location"
  | "dates"
  | "duration_text"
  | "deadline"
  | "compensation"
  | "partner"
  | "partner_display_name"
  | "internal_notes";

export interface OpportunityDraft {
  title: string | null;
  type: "workshop" | "engagement" | "role" | "cofacilitation" | null;
  summary: string | null;
  description_md: string | null;
  topic_slugs: string[];
  location_mode: "remote" | "onsite" | "hybrid" | null;
  city: string | null;
  starts_on: string | null;
  ends_on: string | null;
  duration_text: string | null;
  deadline_on: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  compensation_text: string | null;
  partner_id: number | null;
  suggested_partner: { internal_name: string; display_name: string | null } | null;
  partner_display_name: string | null;
  internal_notes: string | null;
}

export interface DraftResponse {
  draft: OpportunityDraft;
  drafted_fields: DraftedField[];
  cost_usd: number;
  model: string;
}

export async function getDraftConfig(
  adminKey: string,
): Promise<{ available: boolean; model: string }> {
  void adminKey;
  throw new Error("getDraftConfig: not implemented (F6)");
}

export async function draftOpportunity(
  adminKey: string,
  body: { text: string; opportunity_id: number | null; keep_partner_identity: boolean },
): Promise<DraftResponse> {
  void adminKey;
  void body;
  throw new Error("draftOpportunity: not implemented (F6)");
}
