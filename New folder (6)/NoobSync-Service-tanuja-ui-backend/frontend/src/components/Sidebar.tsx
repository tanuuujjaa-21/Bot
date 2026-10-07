import { useMemo, useState } from "react";
import type { Conversation, User } from "../lib/api";
import { groupByDay } from "../lib/dates";
import { CloseIcon, LogoutIcon, PlusIcon, TrashIcon } from "./icons";

interface Props {
  user: User;
  conversations: Conversation[];
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onSignOut: () => void;
  onClose?: () => void;
}

export default function Sidebar({
  user, conversations, loading, activeId, onSelect, onNew, onDelete, onSignOut, onClose,
}: Props) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const groups = useMemo(() => groupByDay(conversations), [conversations]);

  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-4 py-4">
        <button
          type="button"
          onClick={onNew}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-pine px-4 py-2.5 text-sm font-semibold text-white hover:bg-pine-dark"
        >
          <PlusIcon size={16} />
          New chat
        </button>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close chat history"
            className="rounded-lg p-2 text-mute hover:bg-paper lg:hidden"
          >
            <CloseIcon />
          </button>
        )}
      </div>

      <nav aria-label="Chat history" className="scroll-thin flex-1 overflow-y-auto px-2 py-3">
        {loading && <p className="px-3 py-2 text-sm text-mute">Loading your chats</p>}

        {!loading && conversations.length === 0 && (
          <p className="px-3 py-2 text-sm leading-relaxed text-mute">
            Your past chats will be listed here.
          </p>
        )}

        {groups.map((group) => (
          <section key={group.label} className="mb-4">
            <h2 className="px-3 pb-1 font-sans text-xs font-semibold text-mute">{group.label}</h2>
            <ul>
              {group.items.map((c) => {
                const active = c.id === activeId;
                if (confirmingId === c.id) {
                  return (
                    <li
                      key={c.id}
                      className="flex items-center justify-between gap-2 rounded-lg bg-rust-soft px-3 py-2 text-sm"
                    >
                      <span className="truncate text-rust">Delete this chat?</span>
                      <span className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => {
                            setConfirmingId(null);
                            onDelete(c.id);
                          }}
                          className="rounded-md bg-rust px-2.5 py-1 text-xs font-semibold text-white"
                        >
                          Delete
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          className="rounded-md px-2.5 py-1 text-xs font-semibold text-ink hover:bg-white/70"
                        >
                          Keep
                        </button>
                      </span>
                    </li>
                  );
                }
                return (
                  <li key={c.id} className="group relative">
                    <button
                      type="button"
                      onClick={() => onSelect(c.id)}
                      aria-current={active ? "true" : undefined}
                      className={`block w-full truncate rounded-lg py-2 pl-3 pr-10 text-left text-sm ${
                        active ? "bg-pine-soft font-semibold text-pine-dark" : "hover:bg-paper"
                      }`}
                    >
                      {c.title}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(c.id)}
                      aria-label={`Delete chat: ${c.title}`}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-mute opacity-100 hover:bg-rust-soft hover:text-rust focus-visible:opacity-100 lg:opacity-0 lg:group-hover:opacity-100"
                    >
                      <TrashIcon size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>

      <div className="flex items-center gap-3 border-t border-line px-4 py-3">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pine-soft font-display text-sm font-bold text-pine"
          aria-hidden="true"
        >
          {user.name.trim().charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{user.name}</p>
          <p className="truncate text-xs text-mute">{user.phone}</p>
        </div>
        <button
          type="button"
          onClick={onSignOut}
          aria-label="Sign out"
          title="Sign out"
          className="rounded-lg p-2 text-mute hover:bg-paper hover:text-ink"
        >
          <LogoutIcon size={18} />
        </button>
      </div>
    </div>
  );
}
