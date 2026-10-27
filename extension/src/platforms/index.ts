import type { Platform } from "../lib/contract.ts";
import { linkedin } from "./linkedin.ts";
import { naukri } from "./naukri.ts";
import type { PlatformAdapter } from "./types.ts";

export function adapterFor(platform: Platform): PlatformAdapter {
  return platform === "linkedin" ? linkedin : naukri;
}

export type { ObservationDraft, PlatformAdapter } from "./types.ts";