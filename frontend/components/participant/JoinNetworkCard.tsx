import { Card } from "@/components/ui/Card";

/**
 * "Join our network" card for participants. Plain anchor to /network, which is
 * outside the /app basePath. No sign-in and no network call here.
 */
export function JoinNetworkCard() {
  return (
    <Card className="p-4" data-testid="join-network-card">
      <h2 className="text-base font-semibold text-stone-900">Join our network</h2>
      <p className="mt-1 text-sm text-stone-600">
        Get matched with paid training and facilitation opportunities from our community.
      </p>
      <a
        href="/network"
        className="mt-3 inline-block text-sm font-medium text-brand-700 underline underline-offset-4"
      >
        Join our network
      </a>
    </Card>
  );
}
