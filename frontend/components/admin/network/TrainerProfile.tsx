import { formatDate } from "@/lib/format";
import { LEVEL_LABELS, type TrainerDetailProfile } from "@/lib/adminNetwork";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";

const DAYS: Array<[string, string]> = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-xs font-semibold tracking-wide text-stone-500 uppercase">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

const none = <p className="text-sm text-stone-400">Not provided</p>;

/** The trainer's full profile as they entered it (read-only for admins). */
export function TrainerProfile({ trainer: t }: { trainer: TrainerDetailProfile }) {
  const links = [
    ["LinkedIn", t.linkedin_url],
    ["GitHub", t.github_url],
    ["Website", t.website_url],
  ].filter((l): l is [string, string] => Boolean(l[1]));
  const availability = DAYS.map(([key, label]) => {
    const parts = t.availability?.[key];
    return Array.isArray(parts) && parts.length ? `${label}: ${parts.join(", ")}` : null;
  }).filter(Boolean) as string[];

  return (
    <Card className="space-y-5 p-5">
      <h2 className="text-sm font-semibold text-stone-900">Profile</h2>

      <Section title="Bio">
        {t.bio_md?.trim() ? <Markdown className="text-sm text-stone-700">{t.bio_md}</Markdown> : none}
      </Section>

      <Section title="Topics">
        {t.topics.length === 0 ? (
          none
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {t.topics.map((tp) => (
              <Badge key={tp.slug} tone="brand">
                {tp.name}
                <span className="text-brand-500">· {LEVEL_LABELS[tp.level] ?? tp.level}</span>
              </Badge>
            ))}
          </div>
        )}
      </Section>

      <Section title="Past work">
        {t.past_work.length === 0 ? (
          none
        ) : (
          <ul className="space-y-1 text-sm text-stone-700">
            {t.past_work.map((w, i) => (
              <li key={i}>
                <span className="font-medium text-stone-800">{w.title}</span>
                {[w.kind, w.org, w.year].filter(Boolean).length > 0 && (
                  <span className="text-stone-500"> — {[w.kind, w.org, w.year].filter(Boolean).join(" · ")}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Links">
        {links.length === 0 ? (
          none
        ) : (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            {links.map(([label, url]) => (
              <li key={label}>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-brand-700 hover:underline"
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Availability">
        <div className="space-y-1 text-sm text-stone-700">
          <p>
            {t.available_from ? `Available from ${formatDate(t.available_from)}` : "No start date given"}
          </p>
          {availability.length > 0 ? (
            <p className="text-stone-600">{availability.join(" · ")}</p>
          ) : (
            <p className="text-stone-400">No weekly availability marked</p>
          )}
          {t.blackouts.length > 0 && (
            <p className="text-stone-500">
              Unavailable:{" "}
              {t.blackouts
                .map((b) => [b.start, b.end].filter(Boolean).map((d) => formatDate(d as string)).join("–"))
                .join(", ")}
            </p>
          )}
        </div>
      </Section>

      <p className="text-xs text-stone-400">
        {t.consent_at
          ? `Consented to the network terms${t.consent_version ? ` (v${t.consent_version})` : ""} on ${formatDate(t.consent_at)}.`
          : "No consent recorded."}
      </p>
    </Card>
  );
}
