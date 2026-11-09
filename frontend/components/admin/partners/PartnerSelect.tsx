"use client";

import type { PartnerRef } from "@/lib/adminPartners";

/** Stub — F5 fills. */
export function PartnerSelect(props: {
  value: PartnerRef | null;
  onChange: (p: PartnerRef | null) => void;
  suggestedNew?: { internal_name: string; display_name: string | null } | null;
  drafted?: boolean;
  error?: string;
}) {
  void props;
  return null;
}
