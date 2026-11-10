"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { ApiError } from "@/lib/api";
import { formatDate, timeAgo, useNowTick } from "@/lib/format";
import {
  adminRevokeInvite,
  createInvite,
  emailInvite,
  outboxLabel,
  isAuthError,
  listInvites,
  type InviteStatus,
  type NetworkInvite,
} from "@/lib/adminNetwork";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CopyButton } from "@/components/ui/CopyButton";
import { Skeleton } from "@/components/ui/Skeleton";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAdmin } from "@/components/admin/AdminGate";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const LIST_SIZE = 10;

const STATUS: Record<InviteStatus, { tone: BadgeTone; label: string }> = {
  pending: { tone: "warning", label: "Pending" },
  accepted: { tone: "success", label: "Accepted" },
  expired: { tone: "neutral", label: "Expired" },
  revoked: { tone: "neutral", label: "Revoked" },
  superseded: { tone: "neutral", label: "Superseded" },
};

const ALREADY_JOINED = "This email has already joined through an invite.";

function rowDetail(inv: NetworkInvite, now: number): string {
  switch (inv.status) {
    case "accepted":
      return inv.accepted_at ? `accepted ${timeAgo(inv.accepted_at, now)}` : "accepted";
    case "expired":
      return `expired ${formatDate(inv.expires_at)}`;
    case "revoked":
      return inv.revoked_at
        ? `revoked ${timeAgo(inv.revoked_at, now)}${inv.revoked_by ? ` by ${inv.revoked_by}` : ""}`
        : "revoked";
    case "superseded":
      return "Already joined via another invite";
    default:
      return `created ${timeAgo(inv.created_at, now)} · expires ${formatDate(inv.expires_at)}`;
  }
}

function InviteLink({ url }: { url: string }) {
  return (
    <div className="flex items-center gap-2">
      <code
        className="min-w-0 flex-1 truncate rounded-md border border-stone-200 bg-stone-50 px-2 py-1 font-mono text-xs text-stone-700"
        title={url}
        data-testid="invite-url"
      >
        {url}
      </code>
      <CopyButton text={url} label="Copy link" />
    </div>
  );
}

/**
 * Invites panel — create a single-use 14-day `/invite/<token>` link for one
 * email and copy it, or email it with an explicit per-row click (never automatic).
 */
export function InvitesPanel() {
  const { adminKey, onUnauthorized } = useAdmin();
  const now = useNowTick(30000);
  const headingId = useId();
  const emailId = useId();
  const nameId = useId();

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<NetworkInvite | null>(null);
  const [reused, setReused] = useState(false);

  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);

  const [emailTarget, setEmailTarget] = useState<NetworkInvite | null>(null);
  const [emailing, setEmailing] = useState(false);
  const [emailResult, setEmailResult] = useState<Record<number, string>>({});

  const [invites, setInvites] = useState<NetworkInvite[] | null>(null);
  const [total, setTotal] = useState(0);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setListError(null);
    try {
      const page = await listInvites(adminKey, 1, LIST_SIZE);
      setInvites(page.invites);
      setTotal(page.total);
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setListError(err instanceof ApiError ? err.message : "Couldn't load invites.");
    }
  }, [adminKey, onUnauthorized]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!EMAIL_RE.test(cleanEmail)) {
      setFormError("Enter a valid email address.");
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const res = await createInvite(adminKey, {
        email: cleanEmail,
        name: name.trim() || null,
      });
      setCreated(res.invite);
      setReused(res.reused);
      setEmail("");
      setName("");
      void loadList();
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setCreated(null);
      if (err instanceof ApiError && err.code === "invite_already_accepted") {
        setFormError(ALREADY_JOINED);
      } else {
        setFormError(err instanceof ApiError ? err.message : "Couldn't create the invite.");
      }
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (inv: NetworkInvite) => {
    setRevokingId(inv.id);
    setRowError(null);
    try {
      const updated = await adminRevokeInvite(adminKey, inv.id);
      setInvites((cur) => (cur ? cur.map((x) => (x.id === updated.id ? updated : x)) : cur));
      if (created && created.id === updated.id) setCreated(null);
      setConfirmId(null);
      void loadList();
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setRowError({
        id: inv.id,
        message: err instanceof ApiError ? err.message : "Couldn't revoke the invite.",
      });
      void loadList();
    } finally {
      setRevokingId(null);
    }
  };

  const sendEmail = async () => {
    const inv = emailTarget;
    if (!inv) return;
    setEmailing(true);
    setRowError(null);
    try {
      const res = await emailInvite(adminKey, inv.id);
      setEmailResult((cur) => ({ ...cur, [inv.id]: outboxLabel(res.status) }));
      setEmailTarget(null);
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setRowError({
        id: inv.id,
        message: err instanceof ApiError ? err.message : "Couldn't email the invite.",
      });
      setEmailTarget(null);
      void loadList();
    } finally {
      setEmailing(false);
    }
  };

  return (
    <section aria-labelledby={headingId}>
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={headingId} className="text-sm font-semibold text-stone-900">
            Invites
          </h2>
          <span className="text-xs text-stone-400">Single-use · valid 14 days</span>
        </div>
        <p className="mt-1 text-xs text-stone-500">
          Invited trainers start <strong className="font-medium text-stone-700">Verified</strong>{" "}
          when they sign in with the invited email.
        </p>

        <form onSubmit={submit} className="mt-3 space-y-2" noValidate>
          <div>
            <label htmlFor={emailId} className="block text-xs font-medium text-stone-700">
              Email
            </label>
            <input
              id={emailId}
              type="email"
              autoComplete="off"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setFormError(null);
              }}
              placeholder="trainer@example.com"
              aria-invalid={formError ? true : undefined}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor={nameId} className="block text-xs font-medium text-stone-700">
              Name <span className="font-normal text-stone-400">(optional)</span>
            </label>
            <input
              id={nameId}
              type="text"
              autoComplete="off"
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none"
            />
          </div>
          {formError && (
            <p className="text-xs text-red-700" role="alert">
              {formError}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" loading={creating}>
              Create invite
            </Button>
          </div>
        </form>

        {created && (
          <div
            className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/60 p-3"
            data-testid="invite-created"
          >
            {reused && (
              <p className="mb-1.5 text-xs text-emerald-900" data-testid="invite-reused" role="status">
                An invite for this email already existed — its link is renewed for 14 days.
              </p>
            )}
            <p className="mb-1.5 text-xs font-medium text-emerald-800">
              Invite for {created.email} — copy this link and send it yourself:
            </p>
            <InviteLink url={created.url} />
          </div>
        )}

        <div className="mt-4 border-t border-stone-100 pt-3">
          <h3 className="text-xs font-semibold tracking-wide text-stone-500 uppercase">
            Recent invites{total > LIST_SIZE ? ` (latest ${LIST_SIZE} of ${total})` : ""}
          </h3>
          {listError ? (
            <div className="mt-2 text-xs">
              <p className="text-red-700" role="alert">
                {listError}
              </p>
              <Button variant="secondary" size="sm" className="mt-2" onClick={() => void loadList()}>
                Retry
              </Button>
            </div>
          ) : invites === null ? (
            <div className="mt-2 space-y-2" aria-label="Loading invites">
              <Skeleton className="h-9" />
              <Skeleton className="h-9" />
            </div>
          ) : invites.length === 0 ? (
            <p className="mt-2 text-xs text-stone-400">No invites yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-stone-100" data-testid="invite-list">
              {invites.map((inv) => {
                const st = STATUS[inv.status] ?? STATUS.pending;
                return (
                  <li key={inv.id} className="py-2" data-testid="invite-row">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-stone-800" title={inv.email}>
                          {inv.email}
                        </p>
                        <p className="text-xs text-stone-400">
                          {inv.name ? `${inv.name} · ` : ""}
                          {rowDetail(inv, now)}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Badge tone={st.tone}>{st.label}</Badge>
                        {inv.status !== "pending" && (
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled
                            data-testid="invite-email"
                            aria-label={`Email invite to ${inv.email}`}
                            title={
                              inv.status === "expired"
                                ? "Expired - nothing to email"
                                : inv.status === "revoked"
                                  ? "Revoked invites can't be emailed"
                                  : "Already used - can't be emailed"
                            }
                          >
                            Email invite
                          </Button>
                        )}
                        {inv.status === "pending" && (
                          <>
                            <CopyButton
                              text={inv.url}
                              iconOnly
                              title="Copy invite link"
                              aria-label={`Copy invite link for ${inv.email}`}
                            />
                            <Button
                              variant="secondary"
                              size="sm"
                              data-testid="invite-email"
                              aria-label={`Email invite to ${inv.email}`}
                              onClick={() => {
                                setRowError(null);
                                setEmailTarget(inv);
                              }}
                            >
                              Email invite
                            </Button>
                            {confirmId !== inv.id && (
                              <Button
                                variant="secondary"
                                size="sm"
                                data-testid="invite-revoke"
                                aria-label={`Revoke invite for ${inv.email}`}
                                onClick={() => {
                                  setRowError(null);
                                  setConfirmId(inv.id);
                                }}
                              >
                                Revoke
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                    {inv.status === "pending" && confirmId === inv.id && (
                      <div
                        className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-red-200 bg-red-50/60 px-2 py-1.5 text-xs text-red-800"
                        role="alertdialog"
                        aria-label="Confirm revoke"
                      >
                        <span>Revoke this invite? The link will stop working.</span>
                        <Button
                          variant="danger"
                          size="sm"
                          data-testid="invite-revoke-confirm"
                          loading={revokingId === inv.id}
                          onClick={() => void revoke(inv)}
                        >
                          Revoke
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={revokingId === inv.id}
                          onClick={() => setConfirmId(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                    {emailResult[inv.id] && (
                      <p className="mt-1 text-xs text-stone-600" role="status" data-testid="invite-email-result">
                        Email: {emailResult[inv.id]}
                      </p>
                    )}
                    {rowError && rowError.id === inv.id && (
                      <p className="mt-1 text-xs text-red-700" role="alert">
                        {rowError.message}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Card>
      <ConfirmDialog
        open={emailTarget !== null}
        title="Email this invite?"
        body={
          <>
            Send the invite link to <strong>{emailTarget?.email}</strong>? It is one email, sent only
            when you click. Without SMTP configured it is recorded as not sent.
          </>
        }
        confirmLabel="Send email"
        busy={emailing}
        onConfirm={() => void sendEmail()}
        onCancel={() => setEmailTarget(null)}
      />
    </section>
  );
}
