"use client";

import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { StubAction } from "@/components/ui/StubBadge";
import { useAdmin } from "@/components/admin/AdminGate";

const linkCls =
  "rounded-lg px-3 py-1.5 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900";

/** Admin header for the trainer-network pages (pool + trainer detail). */
export function NetworkHeader() {
  const { signOut } = useAdmin();
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
        <Link href="/admin/" className={linkCls}>
          Workshops
        </Link>
        <Link href="/admin/opportunities/" className={linkCls}>
          Opportunities
        </Link>
        <Link href="/admin/topics/" className={linkCls}>
          Topics
        </Link>
        <Link
          href="/admin/network/"
          aria-current="page"
          data-testid="nav-network"
          className="rounded-lg bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-700"
        >
          Trainer network
        </Link>
        <StubAction label="Outbox" />
        <Button variant="ghost" size="sm" onClick={signOut}>
          Sign out
        </Button>
      </nav>
    </header>
  );
}
