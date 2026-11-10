"use client";

import { AdminGate } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { OutboxTable } from "@/components/admin/outbox/OutboxTable";

export default function AdminOutboxPage() {
  return (
    <AdminGate purpose="to view the email outbox">
      <main data-testid="admin-outbox-page" className="mx-auto max-w-6xl px-4 py-8">
        <AdminHeader current="outbox" />
        <h1 className="mb-5 text-2xl font-semibold text-stone-900">Outbox</h1>
        <OutboxTable />
      </main>
    </AdminGate>
  );
}
