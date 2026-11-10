"use client";

import { ListShell } from "@/components/network/applications/ListShell";
import { EmailPrefsCard } from "@/components/network/searches/EmailPrefsCard";
import { SearchList } from "@/components/network/searches/SearchList";

export default function SavedSearchesPage() {
  return (
    <ListShell
      title="Saved searches"
      intro="Get an email when a new opportunity matches one of your searches."
      next="/app/network/searches/"
    >
      {() => (
        <div className="space-y-6">
          <SearchList />
          <EmailPrefsCard />
        </div>
      )}
    </ListShell>
  );
}
