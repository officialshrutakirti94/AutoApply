export function mergeVisitedJobIds(
  pageVisited: Iterable<string>,
  runVisited: unknown,
): Set<string> {
  const visited = new Set(pageVisited);
  if (Array.isArray(runVisited)) {
    for (const id of runVisited) {
      if (typeof id === "string") visited.add(id);
    }
  }
  return visited;
}

export function addVisitedJobId(visited: string[], jobId: string): string[] {
  return visited.includes(jobId) ? visited : [...visited, jobId];
}
