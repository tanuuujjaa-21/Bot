import { useEffect, useRef } from "react";
import type { KeyboardEvent } from "react";
import { QUESTION_MAX } from "../lib/validation";
import { SendIcon } from "./icons";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  /** Changes whenever the composer should grab focus (new/selected chat). */
  focusSignal: string;
}

export default function Composer({ value, onChange, onSend, disabled, focusSignal }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, [focusSignal]);

  // Auto-grow up to ~6 lines, and shrink back after sending.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!disabled && value.trim()) onSend();
    }
  }

  const canSend = !disabled && value.trim().length > 0;
  const nearLimit = value.length >= QUESTION_MAX - 80;

  return (
    <div className="border-t border-line bg-paper px-4 pb-4 pt-3 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-line bg-panel p-2 focus-within:border-pine">
          <label htmlFor="composer" className="sr-only">
            Your question
          </label>
          <textarea
            id="composer"
            ref={ref}
            rows={1}
            value={value}
            maxLength={QUESTION_MAX}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question"
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-3 py-2 leading-normal placeholder:text-mute/60 focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          <button
            type="button"
            onClick={onSend}
            disabled={!canSend}
            aria-label="Send question"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-pine text-white hover:bg-pine-dark disabled:cursor-not-allowed disabled:bg-line disabled:text-mute"
          >
            <SendIcon />
          </button>
        </div>
        <p className="mt-2 flex justify-between px-1 text-xs text-mute">
          <span>Enter sends, Shift+Enter adds a line.</span>
          {nearLimit && (
            <span className={value.length >= QUESTION_MAX ? "text-rust" : undefined}>
              {value.length} / {QUESTION_MAX}
            </span>
          )}
        </p>
      </div>
    </div>
  );
}
