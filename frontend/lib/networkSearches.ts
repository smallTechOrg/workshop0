/** Saved searches + email preferences client. spec/api.md §Phase 13. Stub: slice F2 implements. */

export interface SearchCriteria {
  types: string[];
  topic_slugs: string[];
  location_modes: string[];
  cities: string[];
}

export interface SavedSearch {
  id: number;
  name: string;
  criteria: SearchCriteria;
  alerts_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailPrefs {
  alerts: boolean;
  digest: boolean;
}

const NOT_IMPLEMENTED = "networkSearches: not implemented (Phase 13 slice F2)";

export async function listSearches(): Promise<{ searches: SavedSearch[]; limit: number }> {
  throw new Error(NOT_IMPLEMENTED);
}

export async function createSearch(body: {
  name: string;
  criteria: SearchCriteria;
  alerts_enabled?: boolean;
}): Promise<SavedSearch> {
  void body;
  throw new Error(NOT_IMPLEMENTED);
}

export async function updateSearch(
  id: number,
  body: Partial<{ name: string; criteria: SearchCriteria; alerts_enabled: boolean }>,
): Promise<SavedSearch> {
  void id;
  void body;
  throw new Error(NOT_IMPLEMENTED);
}

export async function deleteSearch(id: number): Promise<{ deleted: boolean }> {
  void id;
  throw new Error(NOT_IMPLEMENTED);
}

export async function getEmailPrefs(): Promise<EmailPrefs> {
  throw new Error(NOT_IMPLEMENTED);
}

export async function setEmailPrefs(body: Partial<EmailPrefs>): Promise<EmailPrefs> {
  void body;
  throw new Error(NOT_IMPLEMENTED);
}
