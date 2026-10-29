export function requiresReconnect(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    error.status === 401
  );
}

export function shouldShowPairingForm(connected: boolean, reconnectRequested: boolean): boolean {
  return !connected || reconnectRequested;
}
