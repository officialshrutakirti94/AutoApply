import assert from "node:assert/strict";
import test from "node:test";
import { requiresReconnect, shouldShowPairingForm } from "./connection-state.ts";

test("a revoked extension token requires pairing again", () => {
  assert.equal(requiresReconnect({ status: 401 }), true);
  assert.equal(requiresReconnect({ status: 403 }), false);
  assert.equal(requiresReconnect(new Error("network unavailable")), false);
});

test("pairing form is available when disconnected or explicitly requested", () => {
  assert.equal(shouldShowPairingForm(false, false), true);
  assert.equal(shouldShowPairingForm(true, true), true);
  assert.equal(shouldShowPairingForm(true, false), false);
});
