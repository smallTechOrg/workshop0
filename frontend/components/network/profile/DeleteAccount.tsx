"use client";

/**
 * Danger zone (capabilities.md C11): **Delete my account** → a confirmation
 * step that requires typing the account email → a distinct **Delete
 * permanently** button → `DELETE /api/me`. Profile, CV and account are removed
 * immediately and the session cookie is cleared; the page then shows the
 * confirmation screen (via `onDeleted`).
 */

import { useId, useState } from "react";
import { ApiError } from "@/lib/api";
import { deleteAccount } from "@/lib/network";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";

export function DeleteAccount({ email, onDeleted }: { email: string; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();

  const matches = typed.trim().toLowerCase() === email.toLowerCase();

  function close() {
    if (busy) return;
    setOpen(false);
    setTyped("");
    setError(null);
  }

  async function confirm() {
    if (!matches) {
      setError("That doesn't match your account email.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(typed.trim());
      setOpen(false);
      onDeleted();
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") {
        setError("That doesn't match your account email.");
      } else if (err instanceof ApiError && err.code === "not_signed_in") {
        setError("Your sign-in has expired — sign in again to delete your account.");
      } else if (err instanceof ApiError && err.code === "network_error") {
        setError("We couldn't reach the server — nothing was deleted; try again.");
      } else {
        setError("Something went wrong on our side — nothing was deleted; try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${inputId}-title`} data-testid="danger-zone">
      <Card className="border-red-200 p-5 sm:p-6">
        <h2 id={`${inputId}-title`} className="font-semibold text-red-800">
          Danger zone
        </h2>
        <p className="mt-1 text-sm text-stone-600">
          Deleting your account removes your profile, your CV and your sign-in immediately. This
          can't be undone.
        </p>
        <Button
          variant="secondary"
          className="mt-4 border-red-300 text-red-700 hover:bg-red-50"
          onClick={() => setOpen(true)}
          data-testid="delete-account"
        >
          Delete my account
        </Button>
      </Card>

      <Modal open={open} onClose={close} title="Delete your account?" widthClassName="max-w-md">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void confirm();
          }}
        >
          <p className="text-sm text-stone-600">
            Your profile, CV and account will be removed straight away and you'll be signed out.
          </p>
          <div>
            <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-stone-800">
              Type your email to confirm
            </label>
            <input
              id={inputId}
              data-testid="delete-confirm-email"
              type="email"
              autoComplete="off"
              value={typed}
              onChange={(e) => {
                setTyped(e.target.value);
                if (error) setError(null);
              }}
              placeholder={email}
              className="block w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-base text-stone-900 shadow-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/20"
            />
          </div>
          {error && (
            <p role="alert" data-testid="delete-error" className="text-sm text-red-700">
              {error}
            </p>
          )}
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={close} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="danger"
              loading={busy}
              disabled={!matches}
              data-testid="delete-confirm"
            >
              Delete permanently
            </Button>
          </div>
        </form>
      </Modal>
    </section>
  );
}
