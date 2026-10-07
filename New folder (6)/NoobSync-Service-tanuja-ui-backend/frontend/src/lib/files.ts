// The file types the uploader accepts. Keep in sync with
// backend/config.py ALLOWED_EXTENSIONS.

export interface FileKind {
  ext: string;      // ".pdf"
  label: string;    // shown on the button
  hint: string;     // what it is good for
  accept: string;   // value for <input accept>
}

export const FILE_KINDS: FileKind[] = [
  { ext: ".pdf", label: "PDF", hint: "Brochures, reports, manuals", accept: ".pdf,application/pdf" },
  {
    ext: ".docx",
    label: "Word",
    hint: "Proposals, policies, FAQs",
    accept: ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  },
  { ext: ".txt", label: "Text", hint: "Plain notes and exports", accept: ".txt,text/plain" },
  { ext: ".md", label: "Markdown", hint: "Docs written in Markdown", accept: ".md,text/markdown" },
  { ext: ".csv", label: "CSV", hint: "Price lists and product tables", accept: ".csv,text/csv" },
];

export const ALL_ACCEPT = FILE_KINDS.map((k) => k.ext).join(",");

export const extOf = (name: string): string => {
  const i = name.lastIndexOf(".");
  return i === -1 ? "" : name.slice(i).toLowerCase();
};

export const isAllowed = (name: string): boolean =>
  FILE_KINDS.some((k) => k.ext === extOf(name));

export const kindLabel = (ext: string): string =>
  FILE_KINDS.find((k) => k.ext === ext)?.label ?? ext.replace(".", "").toUpperCase();

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
