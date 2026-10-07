import type { Message } from "../lib/api";
import { timeLabel } from "../lib/dates";

// Customer chat stays clean by default; sources are for testing/admin use.
const SHOW_SOURCES = import.meta.env.VITE_SHOW_SOURCES === "true";

function sourceNote(message: Message): string | null {
  const s = message.source;
  if (!s) return null;
  if (s.type === "uploaded_document") return `From your files: ${s.files.join(", ")}`;
  if (s.type === "rag_pipeline") return "From the NoobSync knowledge base";
  return null;
}

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const note = !isUser && SHOW_SOURCES ? sourceNote(message) : null;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[88%] sm:max-w-[75%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`whitespace-pre-wrap break-words rounded-2xl px-4 py-3 leading-relaxed ${
            isUser
              ? "rounded-br-md bg-pine text-white"
              : "rounded-bl-md border border-line bg-panel text-ink"
          }`}
        >
          {message.content}
        </div>
        <p className="mt-1 px-1 text-xs text-mute">
          {timeLabel(message.created_at)}
          {note && <span> &nbsp;{note}</span>}
        </p>
      </div>
    </div>
  );
}
