import { useRef, useState } from "react";
import type { DragEvent } from "react";
import type { DocumentsState } from "../hooks/useDocuments";
import { ALL_ACCEPT, FILE_KINDS, formatSize, kindLabel } from "../lib/files";
import { AlertIcon, CheckIcon, CloseIcon, Spinner, UploadIcon } from "./icons";

interface Props {
  docs: DocumentsState;
  onClose?: () => void;
}

export default function DocumentsPanel({ docs, onClose }: Props) {
  const { documents, limits, loaded, uploading, notices, upload, remove, dismissNotices } = docs;
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  // One hidden input serves every button; only its `accept` filter changes.
  function openPicker(accept: string) {
    const input = inputRef.current;
    if (!input) return;
    input.accept = accept;
    input.click();
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    void upload(Array.from(e.dataTransfer.files));
  }

  const full = documents.length >= limits.max_documents;

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-lg font-bold">Your documents</h2>
          <p className="text-sm text-mute">
            {documents.length} of {limits.max_documents} added
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close documents"
            className="rounded-lg p-2 text-mute hover:bg-paper xl:hidden"
          >
            <CloseIcon />
          </button>
        )}
      </header>

      <div className="scroll-thin flex-1 overflow-y-auto px-5 py-5">
        <div
          onDragOver={(e) => e.preventDefault()}
          onDragEnter={() => setDragging(true)}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={onDrop}
          className={`rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors ${
            dragging ? "border-pine bg-pine-soft" : "border-line bg-paper"
          }`}
        >
          <UploadIcon size={26} className="mx-auto text-pine" />
          <p className="mt-2 font-semibold">Drop files here</p>
          <p className="mt-0.5 text-sm text-mute">
            Up to {limits.max_file_mb} MB each, {limits.max_files_per_upload} at a time
          </p>
          <button
            type="button"
            onClick={() => openPicker(ALL_ACCEPT)}
            disabled={uploading || full}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-pine px-4 py-2 text-sm font-semibold text-white hover:bg-pine-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploading && <Spinner size={14} />}
            {uploading ? "Uploading" : "Choose files"}
          </button>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ALL_ACCEPT}
          tabIndex={-1}
          className="sr-only"
          aria-hidden="true"
          onChange={(e) => {
            const picked = Array.from(e.target.files ?? []);
            e.target.value = ""; // lets the same file be chosen again later
            void upload(picked);
          }}
        />

        <fieldset className="mt-5" disabled={uploading || full}>
          <legend className="mb-2 text-sm font-semibold">Or pick a file type</legend>
          <div className="grid grid-cols-2 gap-2">
            {FILE_KINDS.map((kind) => (
              <button
                key={kind.ext}
                type="button"
                onClick={() => openPicker(kind.accept)}
                className="rounded-lg border border-line bg-panel px-3 py-2 text-left hover:border-pine hover:bg-pine-soft disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="block text-sm font-semibold">{kind.label}</span>
                <span className="block text-xs leading-snug text-mute">{kind.hint}</span>
              </button>
            ))}
          </div>
        </fieldset>

        {full && (
          <p className="mt-4 text-sm text-amber-ink">
            You've reached {limits.max_documents} documents. Remove one to add another.
          </p>
        )}

        {notices.length > 0 && (
          <div
            role="alert"
            className="mt-5 rounded-lg border border-rust/30 bg-rust-soft px-3 py-3 text-sm text-rust"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold">Some files weren't added</p>
              <button
                type="button"
                onClick={dismissNotices}
                aria-label="Dismiss"
                className="-m-1 rounded p-1 hover:bg-white/60"
              >
                <CloseIcon size={14} />
              </button>
            </div>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {notices.map((n, i) => (
                <li key={i} className="break-words">
                  {n}
                </li>
              ))}
            </ul>
          </div>
        )}

        <ul className="mt-6 space-y-2" aria-label="Uploaded documents">
          {documents.map((d) => (
            <li
              key={d.id}
              className="flex items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2.5"
            >
              <span className="flex h-9 w-11 shrink-0 items-center justify-center rounded-md bg-pine-soft text-xs font-bold text-pine">
                {kindLabel(d.ext)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold" title={d.filename}>
                  {d.filename}
                </p>
                <p className="flex items-center gap-1.5 text-xs text-mute">
                  {d.status === "processing" && (
                    <>
                      <Spinner size={12} className="text-amber-ink" />
                      <span>Reading the file</span>
                    </>
                  )}
                  {d.status === "ready" && (
                    <>
                      <CheckIcon size={13} className="text-pine" />
                      <span>Ready, {formatSize(d.size_bytes)}</span>
                    </>
                  )}
                  {d.status === "error" && (
                    <>
                      <AlertIcon size={13} className="shrink-0 text-rust" />
                      <span className="text-rust">{d.error ?? "Could not be processed."}</span>
                    </>
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => void remove(d.id)}
                aria-label={`Remove ${d.filename}`}
                className="rounded-md p-1.5 text-mute hover:bg-rust-soft hover:text-rust"
              >
                <CloseIcon size={16} />
              </button>
            </li>
          ))}
        </ul>

        {loaded && documents.length === 0 && (
          <p className="mt-6 text-sm leading-relaxed text-mute">
            No documents yet. Add your own files and I'll look through them first, then fall back
            to NoobSync's built-in knowledge.
          </p>
        )}
      </div>
    </div>
  );
}
