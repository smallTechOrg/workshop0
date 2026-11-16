/**
 * Public opportunity board — `/app/opportunities/` (spec/capabilities.md C10).
 *
 * A server component only so it can export the static head metadata
 * (api.md §Phase 13b); the board itself is the client component `BoardPage`.
 * The metadata lives on this page, not in a layout, so the listing template
 * `opportunities/view/` (whose head the server rewrites) never inherits it.
 */

import type { Metadata } from "next";
import { BoardPage } from "@/components/board/BoardPage";
import { publicPageMetadata } from "@/lib/site";

export const metadata: Metadata = publicPageMetadata({
  title: "Opportunities for AI & tech trainers — Workshop0",
  description:
    "Open workshops, corporate trainings, co-facilitation gigs and roles for trainers in Generative AI, agentic AI and modern tech, curated by smallTech from its partner network. Filter by type and topic and apply in one click.",
  path: "/app/opportunities/",
  image: {
    file: "opportunities.png",
    alt: "Workshop0 Opportunity Board — opportunities for AI & tech trainers",
  },
});

export default function OpportunitiesBoardPage() {
  return <BoardPage />;
}
