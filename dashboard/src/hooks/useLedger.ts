import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Application } from "@/lib/api";
import { split } from "@/lib/buckets";

/**
 * One request, three buckets. The overview and all three pages read the same cache,
 * so the counts can never disagree with the lists.
 */
export function useLedger() {
  const query = useQuery({
    queryKey: ["applications"],
    queryFn: () => api.applications({ limit: 200 }),
    refetchInterval: 15000,
  });

  const items: Application[] = query.data?.items ?? [];
  const buckets = useMemo(() => split(items), [items]);

  return {
    ...query,
    items,
    ...buckets,
    unresolved: query.data?.total_unresolved ?? 0,
    counts: {
      sent: buckets.sent.length,
      waiting: buckets.waiting.length,
      preferred: buckets.preferred.length,
      cantSend: buckets.cantSend.length,
    },
  };
}