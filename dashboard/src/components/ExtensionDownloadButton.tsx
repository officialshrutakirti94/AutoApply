import { Download } from "lucide-react";

const EXTENSION_DOWNLOAD_URL =
  import.meta.env.VITE_EXTENSION_DOWNLOAD_URL || "/autoapply-extension.zip";

export function ExtensionDownloadButton({ compact = false }: { compact?: boolean }) {
  const destination = new URL(EXTENSION_DOWNLOAD_URL, window.location.href);
  const sameOrigin = destination.origin === window.location.origin;

  return (
    <a
      href={EXTENSION_DOWNLOAD_URL}
      download={sameOrigin ? "autoapply-extension.zip" : undefined}
      target={sameOrigin ? undefined : "_blank"}
      rel={sameOrigin ? undefined : "noreferrer"}
      className={`inline-flex items-center justify-center gap-2 rounded-stamp bg-signal font-display font-semibold text-white transition-colors hover:bg-[#ff4b32] ${
        compact ? "h-8 px-3 text-[13px]" : "h-10 px-4 text-[14px]"
      }`}
    >
      <Download size={compact ? 13 : 14} strokeWidth={1.8} />
      Download extension
    </a>
  );
}
