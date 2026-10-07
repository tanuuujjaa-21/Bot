import { useEffect, useRef } from "react";
import type { Message } from "../lib/api";
import MessageBubble from "./MessageBubble";
import { Spinner } from "./icons";

const SUGGESTIONS = [
  "What services does NoobSync offer?",
  "What does ConnectOps do?",
  "How does LaunchOps help with deployment?",
];

interface Props {
  firstName: string;
  messages: Message[];
  loading: boolean;
  sending: boolean;
  pendingQuestion: string | null;
  onSuggest: (question: string) => void;
}

export default function ChatWindow({
  firstName, messages, loading, sending, pendingQuestion, onSuggest,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pendingQuestion, sending, loading]);

  const empty = !loading && messages.length === 0 && !pendingQuestion;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto flex min-h-full max-w-3xl flex-col">
        {loading && (
          <div className="flex flex-1 items-center justify-center text-mute" role="status">
            <Spinner size={22} />
            <span className="sr-only">Loading conversation</span>
          </div>
        )}

        {empty && (
          <div className="my-auto py-10">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Hi {firstName}, what would you like to know?
            </h2>
            <p className="mt-3 max-w-lg text-mute">
              I answer from NoobSync's own documentation and from any files you add. If I can't
              find something, I'll say so.
            </p>
            <ul className="mt-8 flex flex-wrap gap-2.5">
              {SUGGESTIONS.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onClick={() => onSuggest(s)}
                    disabled={sending}
                    className="rounded-full border border-line bg-panel px-4 py-2 text-sm font-medium hover:border-pine hover:bg-pine-soft disabled:opacity-60"
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div role="log" aria-live="polite" aria-label="Conversation" className="space-y-4">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}

          {pendingQuestion && (
            <div className="flex justify-end">
              <div className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-pine px-4 py-3 leading-relaxed text-white sm:max-w-[75%]">
                {pendingQuestion}
              </div>
            </div>
          )}

          {sending && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-line bg-panel px-4 py-4">
                <span className="sr-only">The assistant is writing an answer</span>
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    style={{ animationDelay: `${delay}ms` }}
                    className="h-2 w-2 animate-pulse rounded-full bg-pine motion-reduce:animate-none"
                  />
                ))}
              </div>
            </div>
          )}
        </div>
        <div ref={endRef} />
      </div>
    </div>
  );
}
