import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Loader2, Upload } from "lucide-react";
import { Button, Cell, CellHeader, Chip, Rule, Stamp } from "@/components/ui/primitives";
import { api, HttpError } from "@/lib/api";
import { cn } from "@/lib/cn";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function ResumePage() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const draft = useQuery({ queryKey: ["resume"], queryFn: api.resumeDraft, retry: false });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });

  const upload = useMutationLike();

  function accept(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setMessage(null);
    upload.run(file, {
      onSuccess: async () => {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["resume"] }),
          queryClient.invalidateQueries({ queryKey: ["profile"] }),
        ]);
      },
      onError: (text) => setMessage(text),
    });
  }

  const confidence = Object.entries(draft.data?.confidence ?? {});
  const draftData = (draft.data?.draft ?? {}) as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-[980px]">
      <header className="flex flex-wrap items-end justify-between gap-4 px-1 pb-5 pt-2">
        <div>
          <span className="eyebrow">Your resume</span>
          <h1 className="mt-1.5 font-display text-[26px] font-semibold tracking-[-0.02em]">
            What the agent reads
          </h1>
          <p className="mt-1.5 max-w-[58ch] text-[13px] leading-relaxed text-ink-3">
            Stored privately and only fetched during an active run. Every field below was
            extracted from this file — edit them on your profile if something is off.
          </p>
        </div>
        <Stamp tone={profile.data?.has_resume ? "applied" : "skipped"}>
          {profile.data?.has_resume ? "On file" : "Not uploaded"}
        </Stamp>
      </header>

      <div className="grid gap-3 lg:grid-cols-2">
        <Cell>
          <CellHeader label="File" />
          <div className="flex flex-col gap-4 px-5 py-5">
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                accept(event.dataTransfer.files);
              }}
              className={cn(
                "rounded-cell border border-dashed px-5 py-8 text-center transition-colors",
                dragging ? "border-signal bg-signal/5" : "border-line-strong",
              )}
            >
              {upload.busy ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 size={18} className="animate-spin text-ink-3" />
                  <p className="text-[13px] text-ink-2">Parsing…</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <span className="grid h-9 w-9 place-items-center rounded-stamp border border-line bg-surface-2 text-ink-3">
                    <Upload size={15} strokeWidth={1.7} />
                  </span>
                  <p className="text-[13.5px] text-ink">
                    {profile.data?.has_resume ? "Replace your resume" : "Upload a resume"}
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                    PDF or DOCX · up to 5 MB
                  </p>
                </div>
              )}
            </div>

            <input
              ref={input}
              type="file"
              accept={`.pdf,.docx,application/pdf,${DOCX}`}
              className="sr-only"
              onChange={(event) => accept(event.target.files)}
            />

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" size="sm" onClick={() => input.current?.click()}>
                <FileText size={13} strokeWidth={1.8} />
                Choose file
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={!profile.data?.has_resume}
                onClick={() => api.resumeFileUrl().then((r) => window.open(r.url, "_blank"))}
              >
                <Download size={13} strokeWidth={1.8} />
                Download
              </Button>
            </div>

            {message ? (
              <p className="rounded-stamp border border-danger/40 bg-danger/5 px-3 py-2 text-[12px] text-danger">
                {message}
              </p>
            ) : null}

            {draft.data?.message ? (
              <p className="rounded-stamp border border-ochre/40 bg-ochre/5 px-3 py-2 text-[12px] leading-relaxed text-ochre">
                {draft.data.message}
              </p>
            ) : null}
          </div>
        </Cell>

        <Cell>
          <CellHeader label="Parse confidence" />
          <div className="px-5 py-5">
            {confidence.length ? (
              <>
                <Rule label="Fields" />
                <dl className="mt-3">
                  {confidence.map(([field, level]) => (
                    <div
                      key={field}
                      className="flex items-baseline justify-between gap-4 border-t border-line py-2 first:border-t-0"
                    >
                      <dt className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-3">
                        {field.replace(/_/g, " ")}
                      </dt>
                      <dd
                        className={
                          level === "high"
                            ? "text-[12px] text-moss"
                            : level === "medium"
                              ? "text-[12px] text-ochre"
                              : "text-[12px] text-ink-3"
                        }
                      >
                        {level}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-4 text-[11.5px] leading-relaxed text-ink-3">
                  Anything medium or low is worth checking on your profile.
                </p>
              </>
            ) : (
              <p className="py-6 text-[13px] leading-relaxed text-ink-3">
                No parse yet. Upload a resume and the extracted fields appear here.
              </p>
            )}
          </div>
        </Cell>

        <Cell className="lg:col-span-2">
          <CellHeader label="Extracted content" />
          <div className="flex flex-col gap-4 px-5 py-5">
            {typeof draftData.summary === "string" && draftData.summary ? (
              <div>
                <p className="eyebrow">Summary</p>
                <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">
                  {draftData.summary}
                </p>
              </div>
            ) : null}

            {profile.data?.skills?.length ? (
              <div>
                <p className="eyebrow">Skills</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {profile.data.skills.map((skill) => (
                    <Chip key={skill} className="pointer-events-none">
                      {skill}
                    </Chip>
                  ))}
                </div>
              </div>
            ) : null}

            {!draftData.summary && !profile.data?.skills?.length ? (
              <p className="text-[13px] leading-relaxed text-ink-3">
                Nothing extracted yet.
              </p>
            ) : null}
          </div>
        </Cell>
      </div>
    </div>
  );
}

/** Tiny upload helper so the page has no dependency on TanStack's mutation API shape. */
function useMutationLike() {
  const [busy, setBusy] = useState(false);

  async function run(
    file: File,
    handlers: { onSuccess: () => Promise<void>; onError: (message: string) => void },
  ) {
    setBusy(true);
    try {
      const result = await api.uploadResume(file);
      await handlers.onSuccess();
      if (result.parse_status === "failed") {
        handlers.onError(result.message ?? "We couldn't read this file.");
      }
    } catch (cause) {
      handlers.onError(
        cause instanceof HttpError ? cause.message : "Upload failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return { busy, run };
}