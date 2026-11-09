"use client";

import { useCallback, useEffect, useState } from "react";
import { listPublicTopics, type PublicTopic } from "@/lib/board";

/**
 * The curated topic list for the profile form — `GET /api/public/topics`
 * (active topics only, in curated order; api.md §Phase 10). A profile may only
 * hold these slugs; the drafter is constrained to the same list.
 */
export function useTopics(): {
  topics: PublicTopic[];
  loading: boolean;
  error: string | null;
  retry: () => void;
} {
  const [topics, setTopics] = useState<PublicTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listPublicTopics()
      .then((res) => {
        if (!cancelled) setTopics(res.topics);
      })
      .catch(() => {
        if (!cancelled) setError("We couldn't load the topic list.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { topics, loading, error, retry };
}
