"use client";

import { useState } from "react";
import { cn } from "@/lib/format";
import { initials, type CurrentUser } from "@/lib/networkAuth";

/**
 * The user's Google avatar, or their initials when there is no picture (or it
 * fails to load). `referrerPolicy="no-referrer"` — Google avatar URLs refuse
 * hot-linking with a referrer.
 */
export function Avatar({
  user,
  className,
}: {
  user: Pick<CurrentUser, "display_name" | "email" | "avatar_url">;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  const base = cn("inline-flex shrink-0 items-center justify-center rounded-full", className ?? "size-8");

  if (user.avatar_url && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- static export, external avatar
      <img
        src={user.avatar_url}
        alt=""
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className={cn(base, "object-cover ring-1 ring-stone-200")}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cn(base, "bg-brand-100 text-xs font-semibold text-brand-700 ring-1 ring-brand-200")}
    >
      {initials(user)}
    </span>
  );
}
