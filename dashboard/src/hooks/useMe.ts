import { useQuery } from "@tanstack/react-query";
import { api, type Me } from "@/lib/api";

/** The session, everywhere. `me` is the source of truth for routing. */
export function useMe() {
  return useQuery<Me>({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
    staleTime: 30_000,
  });
}