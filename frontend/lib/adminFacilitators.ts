/** Admin workshop facilitators client. spec/api.md §Phase 13. Stub: slice F5 implements. */

export type FacilitatorRole = "lead" | "co" | "ta";

export interface Facilitator {
  profile_id: number;
  role: FacilitatorRole;
  display_name: string;
  headline: string;
  email: string;
  linked_by: string;
  created_at: string;
}

const NOT_IMPLEMENTED = "adminFacilitators: not implemented (Phase 13 slice F5)";

export async function getFacilitators(
  adminKey: string,
  workshopId: number,
): Promise<{ facilitators: Facilitator[] }> {
  void adminKey;
  void workshopId;
  throw new Error(NOT_IMPLEMENTED);
}

export async function putFacilitators(
  adminKey: string,
  workshopId: number,
  facilitators: { profile_id: number; role: FacilitatorRole }[],
): Promise<{ facilitators: Facilitator[] }> {
  void adminKey;
  void workshopId;
  void facilitators;
  throw new Error(NOT_IMPLEMENTED);
}

export async function addFacilitator(
  adminKey: string,
  workshopId: number,
  body: { profile_id: number; role: FacilitatorRole },
): Promise<{ facilitators: Facilitator[] }> {
  void adminKey;
  void workshopId;
  void body;
  throw new Error(NOT_IMPLEMENTED);
}
