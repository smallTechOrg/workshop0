/** Public trainer directory client. spec/api.md §Phase 13. Stub: slice F3 implements. */

export interface PublicTrainer {
  slug: string;
  display_name: string;
  avatar_url: string | null;
  headline: string;
  city: string | null;
  remote_ok: boolean;
  topics: { slug: string; name: string; level: string }[];
  verified: boolean;
  links: { linkedin: string | null; github: string | null; website: string | null };
  public_url: string;
}

export interface PublicTrainerDetail extends PublicTrainer {
  bio_md: string;
  past_work: { title: string; kind: string; org: string | null; year: number | null }[];
}

const NOT_IMPLEMENTED = "directory: not implemented (Phase 13 slice F3)";

export async function listTrainers(
  topic?: string,
  page?: number,
): Promise<{ items: PublicTrainer[]; page: number; page_size: number; total: number }> {
  void topic;
  void page;
  throw new Error(NOT_IMPLEMENTED);
}

export async function getTrainer(slug: string): Promise<PublicTrainerDetail> {
  void slug;
  throw new Error(NOT_IMPLEMENTED);
}
