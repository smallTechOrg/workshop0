/** Admin partners client — stub (F5 fills). spec/api.md §Phase 11b. */

export interface PartnerRef {
  id: number;
  internal_name: string;
  display_name: string | null;
  active: boolean;
}

export interface AdminPartner extends PartnerRef {
  notes: string | null;
  opportunity_count: number;
  created_at: string;
  updated_at: string;
}

export async function adminListPartners(
  adminKey: string,
): Promise<{ partners: AdminPartner[] }> {
  void adminKey;
  throw new Error("adminListPartners: not implemented (F5)");
}

export async function adminCreatePartner(
  adminKey: string,
  body: { internal_name: string; display_name?: string; notes?: string },
): Promise<{ partner: AdminPartner }> {
  void adminKey;
  void body;
  throw new Error("adminCreatePartner: not implemented (F5)");
}

export async function adminPatchPartner(
  adminKey: string,
  id: number,
  body: Partial<{
    internal_name: string;
    display_name: string;
    notes: string;
    active: boolean;
  }>,
): Promise<{ partner: AdminPartner }> {
  void adminKey;
  void id;
  void body;
  throw new Error("adminPatchPartner: not implemented (F5)");
}
