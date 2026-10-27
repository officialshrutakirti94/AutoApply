import { defineConfig } from "wxt";

/**
 * Manifest V3, React for the popup, the content script limited to the two job
 * platforms.
 *
 * Permissions, and why each one is needed:
 *   storage  - the extension token, and the per-run state that survives a worker restart
 *   power    - keep-awake while a run is active
 *   alarms   - long waits (the 4-10 minute break) without relying on a sleeping timer
 *   tabs     - open the run window, navigate the run tab, detect the tab closing
 */
export default defineConfig({
  srcDir: "src",
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "AutoApply — Apply Magic",
    description:
      "Applies to the jobs that fit on LinkedIn and Naukri, slowly and safely, and tells you when it can't.",
    version: "0.1.0",
    permissions: ["storage", "power", "alarms", "tabs"],
    host_permissions: [
      "*://*.linkedin.com/*",
      "*://*.naukri.com/*",
      // Private resume downloads come from a short-lived signed URL.
      "https://*.supabase.co/*",
    ],
    action: {
      default_title: "AutoApply",
    },
  },
});