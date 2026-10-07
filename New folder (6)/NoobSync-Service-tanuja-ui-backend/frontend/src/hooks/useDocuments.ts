import { useCallback, useEffect, useState } from "react";
import * as api from "../lib/api";
import type { DocumentInfo, UploadLimits } from "../lib/api";
import { formatSize, isAllowed } from "../lib/files";

const DEFAULT_LIMITS: UploadLimits = { max_file_mb: 15, max_documents: 20, max_files_per_upload: 10 };
const POLL_MS = 2000;

export function useDocuments() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [limits, setLimits] = useState<UploadLimits>(DEFAULT_LIMITS);
  const [loaded, setLoaded] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notices, setNotices] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const res = await api.listDocuments();
      setDocuments(res.documents);
      setLimits(res.limits);
    } catch {
      /* a 401 is handled globally; other failures retry on the next poll */
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while something is still being read and embedded.
  const hasProcessing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, refresh]);

  const upload = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      const problems: string[] = [];
      const maxBytes = limits.max_file_mb * 1024 * 1024;
      const valid: File[] = [];

      for (const f of files) {
        if (!isAllowed(f.name)) problems.push(`${f.name}: unsupported file type.`);
        else if (f.size === 0) problems.push(`${f.name}: the file is empty.`);
        else if (f.size > maxBytes)
          problems.push(`${f.name}: ${formatSize(f.size)} is over the ${limits.max_file_mb} MB limit.`);
        else valid.push(f);
      }

      let batch = valid;
      if (valid.length > limits.max_files_per_upload) {
        batch = valid.slice(0, limits.max_files_per_upload);
        problems.push(
          `Only ${limits.max_files_per_upload} files can be added at a time. ` +
            `${valid.length - batch.length} not uploaded.`,
        );
      }

      if (batch.length > 0) {
        setUploading(true);
        try {
          const res = await api.uploadDocuments(batch);
          setDocuments((prev) => [...res.documents, ...prev]);
          res.rejected.forEach((r) => problems.push(`${r.filename}: ${r.error}`));
        } catch (err) {
          problems.push(err instanceof Error ? err.message : "Upload failed. Please try again.");
        } finally {
          setUploading(false);
        }
      }
      setNotices(problems);
    },
    [limits],
  );

  const remove = useCallback(
    async (id: string) => {
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      try {
        await api.deleteDocument(id);
      } catch (err) {
        setNotices([err instanceof Error ? err.message : "Could not remove that file."]);
        void refresh();
      }
    },
    [refresh],
  );

  const dismissNotices = useCallback(() => setNotices([]), []);

  return { documents, limits, loaded, uploading, notices, upload, remove, dismissNotices };
}

export type DocumentsState = ReturnType<typeof useDocuments>;
