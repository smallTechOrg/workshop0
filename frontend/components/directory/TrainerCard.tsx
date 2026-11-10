import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { PublicTrainer } from "@/lib/directory";

export function TrainerAvatar({ name, url, size = "size-12" }: { name: string; url: string | null; size?: string }) {
  if (url && /^https?:\/\//i.test(url)) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${size} shrink-0 rounded-full object-cover`} referrerPolicy="no-referrer" />;
  }
  return (
    <span
      aria-hidden="true"
      className={`${size} inline-flex shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700`}
    >
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  );
}

export function VerifiedBadge() {
  return (
    <Badge tone="success" data-testid="verified-badge">
      ✓ Verified
    </Badge>
  );
}

export function TrainerCard({ trainer }: { trainer: PublicTrainer }) {
  const where = [trainer.city, trainer.remote_ok ? "Remote OK" : null].filter(Boolean).join(" · ");
  return (
    <Card data-testid="trainer-card" className="flex flex-col gap-3 p-5">
      <div className="flex items-center gap-3">
        <TrainerAvatar name={trainer.display_name} url={trainer.avatar_url} />
        <div className="min-w-0">
          <h2 className="truncate font-semibold text-stone-900">
            <a href={trainer.public_url} className="hover:underline">
              {trainer.display_name}
            </a>
          </h2>
          {trainer.verified && <VerifiedBadge />}
        </div>
      </div>
      {trainer.headline && <p className="text-sm text-stone-700">{trainer.headline}</p>}
      {where && <p className="text-xs text-stone-500">{where}</p>}
      {trainer.topics.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {trainer.topics.map((t) => (
            <li key={t.slug}>
              <Badge tone="brand">{t.name}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
