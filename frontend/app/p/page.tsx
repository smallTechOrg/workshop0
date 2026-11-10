"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";
import {
  ApiError,
  completeMilestone,
  participantContent,
  participantReplyHelp,
  participantReopenHelp,
  participantResolveHelp,
  participantState,
  prettyParticipantUrl,
  submitHelp,
  uncompleteMilestone,
  type ContentPayload,
  type StatePayload,
  type TrackerHelpRequest,
} from "@/lib/api";
import { usePoll } from "@/lib/poll";
import { useNowTick } from "@/lib/format";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ConnectionIndicator } from "@/components/ui/ConnectionIndicator";
import { useToast } from "@/components/ui/Toast";
import { MilestoneList } from "@/components/participant/MilestoneList";
import { Markdown } from "@/components/ui/Markdown";
import { Leaderboard } from "@/components/participant/Leaderboard";
import { HelpPanel } from "@/components/participant/HelpPanel";
import { RoomQuestions } from "@/components/participant/RoomQuestions";
import { ProfileCard } from "@/components/participant/ProfileCard";
import { JoinNetworkCard } from "@/components/participant/JoinNetworkCard";
import { BroadcastBanner } from "@/components/participant/BroadcastBanner";

function TrackerSkeleton() {
  return (
    <div className="min-h-screen">
      <div className="border-b border-stone-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </main>
    </div>
  );
}

function ErrorScreen({ title, hint }: { title: string; hint: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-lg p-8 text-center">
        <p aria-hidden="true" className="text-3xl">
          🧭
        </p>
        <h1 className="mt-2 text-xl font-semibold text-stone-900">{title}</h1>
        <p className="mt-2 text-stone-500">{hint}</p>
      </Card>
    </main>
  );
}

function TrackerInner() {
  const params = useSearchParams();
  const token = params.get("t");
  const toast = useToast();
  const nowMs = useNowTick(30000);

  // ---- state poll (3 s visible / 15 s hidden) -----------------------------
  const fetcher = useCallback(
    (v: number) => participantState(token as string, v),
    [token],
  );
  const { data, contentVersion, reconnecting, fatalError, pollNow } =
    usePoll<StatePayload>(token ? fetcher : null, {
      visibleMs: 3000,
      hiddenMs: 15000,
    });

  // ---- milestone bodies (content endpoint, keyed by content_version) ------
  const [content, setContent] = useState<ContentPayload | null>(null);
  const contentCvRef = useRef(-1);
  const [contentRetry, setContentRetry] = useState(0);
  useEffect(() => {
    if (!token || contentVersion < 0) return;
    if (contentCvRef.current >= contentVersion) return;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    participantContent(token, contentCvRef.current)
      .then((res) => {
        if (cancelled) return;
        contentCvRef.current = res.content_version;
        if (res.changed) setContent(res);
      })
      .catch(() => {
        if (cancelled) return;
        retryTimer = setTimeout(() => setContentRetry((x) => x + 1), 3000);
      });
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [token, contentVersion, contentRetry]);

  const contentById = useMemo(() => {
    if (!content) return null;
    return new Map(content.milestones.map((m) => [m.id, m.content_md]));
  }, [content]);

  // ---- optimistic completion overlay --------------------------------------
  const [overlay, setOverlay] = useState<Record<number, boolean>>({});
  useEffect(() => {
    if (!data) return;
    setOverlay((prev) => {
      const base = new Set(data.me.completed_milestone_ids);
      const next: Record<number, boolean> = {};
      let changed = false;
      for (const [k, v] of Object.entries(prev)) {
        if (base.has(Number(k)) === v) {
          changed = true; // server agrees — drop the overlay entry
        } else {
          next[Number(k)] = v;
        }
      }
      return changed ? next : prev;
    });
  }, [data]);

  const completedIds = useMemo(() => {
    const s = new Set(data?.me.completed_milestone_ids ?? []);
    for (const [k, v] of Object.entries(overlay)) {
      if (v) s.add(Number(k));
      else s.delete(Number(k));
    }
    return s;
  }, [data, overlay]);

  const currentId = useMemo(() => {
    const ordered = [...(data?.milestones ?? [])].sort(
      (a, b) => a.position - b.position,
    );
    for (const m of ordered) {
      if (!completedIds.has(m.id)) return m.id;
    }
    return null;
  }, [data, completedIds]);

  const onToggle = async (milestoneId: number, next: boolean, input?: string) => {
    if (!token) return;
    // Gated milestones validate server-side; don't show the optimistic tick
    // until the completion actually lands, or a rejected input would flicker on.
    const optimistic = next && input === undefined;
    if (optimistic || !next) {
      setOverlay((prev) => ({ ...prev, [milestoneId]: next }));
    }
    try {
      if (next) await completeMilestone(token, milestoneId, input);
      else await uncompleteMilestone(token, milestoneId);
      pollNow();
    } catch (err) {
      setOverlay((prev) => {
        const copy = { ...prev };
        delete copy[milestoneId];
        return copy;
      });
      toast.show(
        err instanceof ApiError
          ? `Couldn't save that — ${err.message}`
          : "Couldn't save that — check your connection and try again.",
        "error",
      );
      throw err;
    }
  };

  // ---- optimistic help ----------------------------------------------------
  const [helpSubmitting, setHelpSubmitting] = useState(false);
  const [tempHelp, setTempHelp] = useState<{
    message: string;
    created_at: string;
    minVersion: number | null;
  } | null>(null);
  const [resolvedOverride, setResolvedOverride] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!data) return;
    // Prune the temp entry once the poll payload includes the real request.
    setTempHelp((prev) =>
      prev && prev.minVersion !== null && data.version >= prev.minVersion
        ? null
        : prev,
    );
    // Prune resolve overrides the server now reflects.
    setResolvedOverride((prev) => {
      const stillPending = new Set(
        [...prev].filter((id) =>
          data.help_requests.some((r) => r.id === id && r.status !== "resolved"),
        ),
      );
      return stillPending.size === prev.size ? prev : stillPending;
    });
  }, [data]);

  const helpRequests: TrackerHelpRequest[] = useMemo(() => {
    let merged = (data?.help_requests ?? []).map((r) =>
      resolvedOverride.has(r.id) ? { ...r, status: "resolved" as const } : r,
    );
    if (tempHelp) {
      merged = [
        {
          id: -1,
          message: tempHelp.message,
          status: "open" as const,
          escalated: false,
          milestone_id: null,
          created_at: tempHelp.created_at,
          answers: [],
        },
        ...merged,
      ];
    }
    return merged;
  }, [data, tempHelp, resolvedOverride]);

  const onSubmitHelp = async (message: string): Promise<boolean> => {
    if (!token) return false;
    setHelpSubmitting(true);
    setTempHelp({
      message,
      created_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      minVersion: null,
    });
    try {
      const res = await submitHelp(token, message);
      setTempHelp((prev) => (prev ? { ...prev, minVersion: res.version } : prev));
      pollNow();
      return true;
    } catch (err) {
      setTempHelp(null);
      toast.show(
        err instanceof ApiError
          ? `Couldn't send that — ${err.message}`
          : "Couldn't send that — check your connection and try again.",
        "error",
      );
      return false;
    } finally {
      setHelpSubmitting(false);
    }
  };

  const onReplyHelp = async (id: number, message: string): Promise<boolean> => {
    if (!token) return false;
    try {
      await participantReplyHelp(token, id, message);
      pollNow();
      return true;
    } catch (err) {
      toast.show(
        err instanceof ApiError
          ? `Couldn't send that — ${err.message}`
          : "Couldn't send that — check your connection and try again.",
        "error",
      );
      return false;
    }
  };

  const onResolveHelp = async (id: number) => {
    if (!token) return;
    setResolvedOverride((prev) => new Set(prev).add(id));
    try {
      await participantResolveHelp(token, id);
      pollNow();
    } catch (err) {
      setResolvedOverride((prev) => {
        const copy = new Set(prev);
        copy.delete(id);
        return copy;
      });
      toast.show(
        err instanceof ApiError
          ? `Couldn't resolve that — ${err.message}`
          : "Couldn't resolve that — check your connection and try again.",
        "error",
      );
    }
  };

  const onReopenHelp = async (id: number) => {
    if (!token) return;
    setResolvedOverride((prev) => {
      const copy = new Set(prev);
      copy.delete(id);
      return copy;
    });
    try {
      await participantReopenHelp(token, id);
      pollNow();
    } catch (err) {
      toast.show(
        err instanceof ApiError
          ? `Couldn't reopen that — ${err.message}`
          : "Couldn't reopen that — check your connection and try again.",
        "error",
      );
    }
  };

  // ---- render -------------------------------------------------------------
  if (!token) {
    return (
      <ErrorScreen
        title="This personal link isn't valid"
        hint="The link is missing its key. Use the exact personal link you saved, or ask your facilitator to copy it from the dashboard."
      />
    );
  }
  if (fatalError) {
    return (
      <ErrorScreen
        title="This personal link isn't valid"
        hint="Ask your facilitator to copy your personal link from the dashboard — that link is your key on any device."
      />
    );
  }
  if (!data) return <TrackerSkeleton />;

  const total = data.me.total_count;
  const doneCount = completedIds.size;
  const progressPct = total > 0 ? (doneCount / total) * 100 : 0;
  const personalUrl =
    typeof window === "undefined" ? "" : prettyParticipantUrl(token);
  const archived = data.workshop.status === "archived";

  return (
    <div data-testid="tracker-page" className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
          <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-stone-900">
            {data.workshop.name}
          </h1>
          <ConnectionIndicator reconnecting={reconnecting} />
          <div className="flex items-center gap-2">
            <div className="w-36 shrink-0">
              <ProgressBar
                value={progressPct}
                data-testid="progress-bar"
                label="Your progress"
              />
            </div>
            <span className="text-sm font-medium whitespace-nowrap text-stone-600 tabular-nums">
              {doneCount} / {total}
            </span>
          </div>
        </div>
      </header>

      <BroadcastBanner broadcast={data.broadcast} />

      {data.workshop.paused && (
        <div
          role="status"
          data-testid="paused-banner"
          className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm font-medium text-amber-800"
        >
          The facilitator paused the workshop — completions are locked for a moment.
        </div>
      )}
      {archived && (
        <div
          role="status"
          className="border-b border-stone-200 bg-stone-100 px-4 py-2 text-center text-sm font-medium text-stone-600"
        >
          This workshop has ended — you're browsing the archive.
        </div>
      )}

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <ProfileCard
            token={token}
            me={data.me}
            joinForm={data.join_form ?? []}
            personalUrl={personalUrl}
            archived={archived}
            onSaved={pollNow}
          />
          {content && content.workshop.description_md.trim() !== "" && (
            <Card className="p-4" data-testid="workshop-description">
              <Markdown className="text-sm">{content.workshop.description_md}</Markdown>
            </Card>
          )}
          <MilestoneList
            milestones={data.milestones}
            contentById={contentById}
            completedIds={completedIds}
            currentId={currentId}
            paused={data.workshop.paused || archived}
            submittedInputs={data.me.milestone_inputs ?? {}}
            onToggle={onToggle}
          />
          {total > 0 && doneCount >= total && <JoinNetworkCard />}
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <HelpPanel
              requests={helpRequests}
              nowMs={nowMs}
              submitting={helpSubmitting}
              archived={archived}
              onSubmit={onSubmitHelp}
              onReply={onReplyHelp}
              onResolve={onResolveHelp}
              onReopen={onReopenHelp}
            />
            <RoomQuestions
              token={token}
              openCount={data.room_open_help_count ?? 0}
              nowMs={nowMs}
            />
          </Card>
          <Card className="p-4">
            <h2 className="mb-2 text-base font-semibold text-stone-900">
              Leaderboard
            </h2>
            <Leaderboard
              rows={data.leaderboard}
              me={data.me}
              participantsCount={data.participants_count ?? data.leaderboard.length}
            />
          </Card>
        </div>
      </main>
    </div>
  );
}

export default function TrackerPage() {
  return (
    <Suspense fallback={<TrackerSkeleton />}>
      <TrackerInner />
    </Suspense>
  );
}
