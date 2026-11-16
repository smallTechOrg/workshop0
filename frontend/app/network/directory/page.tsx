/**
 * Public trainer directory — `/app/network/directory/` (also reached via the
 * pretty `/trainers`; spec/capabilities.md C18).
 *
 * A server component only so it can export the static head metadata
 * (api.md §Phase 13b); the directory itself is the client component
 * `DirectoryPage`.
 */

import type { Metadata } from "next";
import { DirectoryPage } from "@/components/directory/DirectoryPage";
import { publicPageMetadata } from "@/lib/site";

export const metadata: Metadata = publicPageMetadata({
  title: "Trainer directory — AI & tech trainers — Workshop0",
  description:
    "Browse trainers in Generative AI, agentic AI, data and modern tech from the smallTech Trainer Network. Filter by topic and open a profile to see their topics, experience and past workshops.",
  path: "/app/network/directory/",
});

export default function TrainerDirectoryPage() {
  return <DirectoryPage />;
}
