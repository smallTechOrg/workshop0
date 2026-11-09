"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import {
  adminCreateTopic,
  adminListTopics,
  adminPatchTopic,
  type AdminTopic,
} from "@/lib/adminBoard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { TopicRow, topicErrorMessage } from "@/components/admin/TopicRow";

function TopicsSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading topics">
      {[0, 1, 2].map((i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      ))}
    </div>
  );
}

function TopicsManager() {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();

  const [topics, setTopics] = useState<AdminTopic[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);

  const [confirmTopic, setConfirmTopic] = useState<AdminTopic | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await adminListTopics(adminKey);
      setTopics(res.topics);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setLoadError("Couldn't load topics — check your connection and try again.");
    }
  }, [adminKey, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  const categories = useMemo(() => {
    const seen: string[] = [];
    for (const t of [...(topics ?? [])].sort((a, b) => a.position - b.position)) {
      if (!seen.includes(t.category)) seen.push(t.category);
    }
    return seen;
  }, [topics]);

  const groups = useMemo(() => {
    const map = new Map<string, AdminTopic[]>();
    for (const t of [...(topics ?? [])].sort((a, b) => a.position - b.position)) {
      const list = map.get(t.category) ?? [];
      list.push(t);
      map.set(t.category, list);
    }
    return [...map.entries()];
  }, [topics]);

  const replaceTopic = (t: AdminTopic) =>
    setTopics((prev) => (prev ? prev.map((x) => (x.id === t.id ? t : x)) : prev));

  const add = async () => {
    const n = name.trim();
    const c = category.trim();
    if (n.length < 2) {
      setAddError("Enter a topic name (at least 2 characters).");
      return;
    }
    if (c.length < 2) {
      setAddError("Choose or type a category (at least 2 characters).");
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      const res = await adminCreateTopic(adminKey, { name: n, category: c });
      setTopics((prev) => [...(prev ?? []), res.topic]);
      setHighlightId(res.topic.id);
      setName("");
      toast.show(`Added “${res.topic.name}”`, "success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setAddError(topicErrorMessage(err, n));
    } finally {
      setAdding(false);
    }
  };

  const setActive = async (t: AdminTopic, active: boolean) => {
    setTogglingId(t.id);
    try {
      const res = await adminPatchTopic(adminKey, t.id, { active });
      replaceTopic(res.topic);
      toast.show(
        active ? `“${t.name}” is active again` : `“${t.name}” deactivated`,
        "success",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      toast.show(topicErrorMessage(err, t.name), "error");
    } finally {
      setTogglingId(null);
    }
  };

  const activeCount = topics?.filter((t) => t.active).length ?? 0;

  return (
    <main data-testid="admin-topics-page" className="mx-auto max-w-4xl px-4 py-8">
      <AdminHeader current="topics" />

      <div className="mb-5">
        <Link
          href="/admin/opportunities/"
          className="text-sm font-medium text-stone-500 hover:text-stone-800"
        >
          ← Opportunities
        </Link>
        <h1 className="mt-1 text-2xl font-semibold text-stone-900">Topics</h1>
        <p className="mt-1 text-sm text-stone-500">
          The shared vocabulary for tagging listings and filtering the public board.
          {topics && (
            <>
              {" "}
              {topics.length} topics · {activeCount} active.
            </>
          )}
        </p>
      </div>

      <Card className="mb-6 p-5">
        <h2 className="mb-3 text-sm font-semibold text-stone-700">Add topic</h2>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            void add();
          }}
        >
          <div className="flex-1">
            <label htmlFor="topic-name" className="mb-1 block text-sm font-medium text-stone-700">
              Name
            </label>
            <input
              id="topic-name"
              data-testid="topic-name-input"
              value={name}
              maxLength={80}
              onChange={(e) => {
                setName(e.target.value);
                if (addError) setAddError(null);
              }}
              placeholder="Elixir"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
            />
          </div>
          <div className="sm:w-56">
            <label htmlFor="topic-category" className="mb-1 block text-sm font-medium text-stone-700">
              Category
            </label>
            <input
              id="topic-category"
              data-testid="topic-category-input"
              list="topic-categories"
              value={category}
              maxLength={48}
              onChange={(e) => {
                setCategory(e.target.value);
                if (addError) setAddError(null);
              }}
              placeholder="Languages"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
            />
            <datalist id="topic-categories">
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <Button type="submit" data-testid="topic-add-button" loading={adding}>
            Add topic
          </Button>
        </form>
        {addError && (
          <p role="alert" data-testid="topic-error" className="mt-2 text-sm text-red-600">
            {addError}
          </p>
        )}
        <p className="mt-2 text-xs text-stone-500">
          The slug is derived from the name and never changes.
        </p>
      </Card>

      {loadError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {loadError}
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : topics === null ? (
        <TopicsSkeleton />
      ) : topics.length === 0 ? (
        <EmptyState
          icon="🏷️"
          title="No topics yet — add the first one above."
          hint="Listings need at least one topic before they can be saved."
        />
      ) : (
        <div className="space-y-6">
          {groups.map(([cat, list]) => (
            <section key={cat} aria-labelledby={`cat-${cat}`}>
              <h2
                id={`cat-${cat}`}
                className="mb-2 text-sm font-semibold tracking-wide text-stone-500 uppercase"
              >
                {cat} <span className="font-normal normal-case">· {list.length}</span>
              </h2>
              <ul className="divide-y divide-stone-100 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
                {list.map((t) => (
                  <TopicRow
                    key={t.id}
                    topic={t}
                    adminKey={adminKey}
                    categories={categories}
                    highlight={t.id === highlightId}
                    onUpdated={(u) => {
                      replaceTopic(u);
                      toast.show(`Saved “${u.name}”`, "success");
                    }}
                    onUnauthorized={onUnauthorized}
                    toggling={togglingId === t.id}
                    onRequestToggle={(topic) => {
                      if (topic.active) setConfirmTopic(topic);
                      else void setActive(topic, true);
                    }}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={confirmTopic !== null}
        title={confirmTopic ? `Deactivate “${confirmTopic.name}”?` : "Deactivate topic?"}
        body="Hidden from filters and pickers; listings already tagged keep it."
        confirmLabel="Deactivate"
        danger
        busy={confirmTopic !== null && togglingId === confirmTopic.id}
        onCancel={() => setConfirmTopic(null)}
        onConfirm={async () => {
          if (!confirmTopic) return;
          await setActive(confirmTopic, false);
          setConfirmTopic(null);
        }}
      />
    </main>
  );
}

export default function AdminTopicsPage() {
  return (
    <AdminGate purpose="to manage topics">
      <TopicsManager />
    </AdminGate>
  );
}
