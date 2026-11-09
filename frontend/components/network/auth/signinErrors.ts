/**
 * Human messages for the callback's `?error=<code>` (spec/api.md §Phase 11 →
 * `GET /api/auth/google/callback`) — plus the start endpoint's JSON codes, in
 * case a caller forwards them.
 */
type SigninMessage = { title: string; hint: string | null };

const MESSAGES: Record<string, SigninMessage> = {
  state_mismatch: {
    title: "That sign-in link expired.",
    hint: "Sign-in has to finish within 10 minutes, in the same browser it started in. Please try again.",
  },
  email_unverified: {
    title: "That Google account's email isn't verified.",
    hint: "Verify the address with Google first, or continue with a different Google account.",
  },
  idp_error: {
    title: "Google couldn't complete the sign-in.",
    hint: "This is usually temporary, or the sign-in was cancelled. Please try again.",
  },
  // Overridden below when the callback supplies the masked `invite_email`.
  invite_email_mismatch: {
    title: "This invite was sent to a different email address — sign in with that Google account.",
    hint: null,
  },
  invite_expired: {
    title: "This invite has expired — ask smallTech for a new one.",
    hint: "You can still join the network without an invite.",
  },
  rate_limited: {
    title: "Too many sign-in attempts.",
    hint: "Wait a minute, then try again.",
  },
  signin_not_configured: {
    title: "Sign-in isn't set up on this server yet.",
    hint: "The operator hasn't added Google sign-in credentials.",
  },
};

/**
 * `inviteEmail` is the callback's masked `invite_email` param (e.g.
 * `as***@example.com`), used only for `invite_email_mismatch` (capabilities.md C11).
 */
export function signinErrorMessage(code: string, inviteEmail?: string | null): SigninMessage {
  const masked = inviteEmail?.trim();
  if (code === "invite_email_mismatch" && masked) {
    return {
      title: `This invite was sent to ${masked} — sign in with that Google account.`,
      hint: null,
    };
  }
  return (
    MESSAGES[code] ?? {
      title: "Sign-in didn't complete.",
      hint: "Something went wrong on our side. Please try again.",
    }
  );
}
