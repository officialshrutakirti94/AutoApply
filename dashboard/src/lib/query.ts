import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The dashboard is polling-based: a refetch on window focus is cheap and
      // makes the app feel live without a socket.
      refetchOnWindowFocus: true,
      staleTime: 10_000,
      retry: (failureCount, error) => {
        // Never retry auth failures: the guard needs to see them immediately.
        const status = (error as { status?: number } | null)?.status;
        if (status === 401 || status === 403 || status === 404) return false;
        return failureCount < 2;
      },
    },
  },
});