"use client";

import Link from "next/link";
import { cn } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { StubAction } from "@/components/ui/StubBadge";
import { useAdmin } from "@/components/admin/AdminGate";

type Section = "opportunities" | "topics";

/** Shared header for the admin board pages (opportunities, editor, topics). */
export function AdminHeader({ current }: { current: Section }) {
  const { signOut } = useAdmin();
  const linkCls = (active: boolean) =>
    cn(
      "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
      active
        ? "bg-brand-50 text-brand-700"
        : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
    );

  return (
    <header className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 pb-4">
      <Link href="/admin/" className="flex items-center gap-2 rounded-lg" title="Admin Home">
        <span aria-hidden="true" className="text-2xl">
          ⛵
        </span>
        <span className="text-xl font-semibold text-stone-900">Workshop0</span>
        <span className="ml-1 hidden text-sm text-stone-400 sm:inline">Admin</span>
      </Link>
      <nav aria-label="Admin sections" className="flex flex-wrap items-center gap-1.5">
        <Link href="/admin/" className={linkCls(false)}>
          Workshops
        </Link>
        <Link
          href="/admin/opportunities/"
          className={linkCls(current === "opportunities")}
          aria-current={current === "opportunities" ? "page" : undefined}
        >
          Opportunities
        </Link>
        <Link
          href="/admin/topics/"
          data-testid="nav-topics"
          className={linkCls(current === "topics")}
          aria-current={current === "topics" ? "page" : undefined}
        >
          Topics
        </Link>
        <StubAction label="Trainer pool" />
        <StubAction label="Outbox" />
        <Button variant="ghost" size="sm" onClick={signOut}>
          Sign out
        </Button>
      </nav>
    </header>
  );
}
