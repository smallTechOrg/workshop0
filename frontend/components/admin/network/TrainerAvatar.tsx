import { cn } from "@/lib/format";
import { initials } from "@/lib/adminNetwork";

/** Avatar image with an initials fallback. */
export function TrainerAvatar({
  name,
  src,
  size = "md",
}: {
  name: string;
  src?: string | null;
  size?: "md" | "lg";
}) {
  const cls = size === "lg" ? "size-14 text-lg" : "size-8 text-xs";
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        referrerPolicy="no-referrer"
        className={cn("shrink-0 rounded-full border border-stone-200 object-cover", cls)}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700",
        cls,
      )}
    >
      {initials(name)}
    </span>
  );
}
