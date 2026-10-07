import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import type { Conversation, Message, User } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useDocuments } from "../hooks/useDocuments";
import ChatWindow from "./ChatWindow";
import Composer from "./Composer";
import DocumentsPanel from "./DocumentsPanel";
import Sidebar from "./Sidebar";
import { AlertIcon, FolderIcon, MenuIcon } from "./icons";

export default function ChatLayout({ user }: { user: User }) {
  const { signOut } = useAuth();
  const docs = useDocuments();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);

  // Which conversation is on screen right now. Lets a slow answer arrive for a
  // chat the visitor has already left without being pasted into the wrong one.
  const activeRef = useRef<string | null>(null);
  const activate = useCallback((id: string | null) => {
    activeRef.current = id;
    setActiveId(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listConversations()
      .then((r) => !cancelled && setConversations(r.conversations))
      .catch(() => undefined)
      .finally(() => !cancelled && setLoadingList(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const selectConversation = useCallback(
    async (id: string) => {
      activate(id);
      setNavOpen(false);
      setMessages([]);
      setError(null);
      setDraft("");
      setLoadingMessages(true);
      try {
        const res = await api.getConversation(id);
        if (activeRef.current === id) setMessages(res.messages);
      } catch (err) {
        if (activeRef.current === id) {
          setError(err instanceof Error ? err.message : "Could not open that chat.");
        }
      } finally {
        if (activeRef.current === id) setLoadingMessages(false);
      }
    },
    [activate],
  );

  const newChat = useCallback(() => {
    activate(null);
    setMessages([]);
    setError(null);
    setDraft("");
    setLoadingMessages(false);
    setNavOpen(false);
  }, [activate]);

  async function deleteChat(id: string) {
    try {
      await api.deleteConversation(id);
      setConversations((list) => list.filter((c) => c.id !== id));
      if (activeRef.current === id) newChat();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that chat.");
    }
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || sending) return;

    setSending(true);
    setError(null);
    setPendingQuestion(question);
    setDraft("");

    try {
      let cid = activeRef.current;
      if (!cid) {
        const { conversation } = await api.createConversation();
        cid = conversation.id;
        activate(cid);
      }
      const res = await api.ask(cid, question);

      if (activeRef.current === cid) {
        setMessages((m) => [...m, res.user_message, res.assistant_message]);
      }
      const answeredId = cid;
      setConversations((list) => {
        const existing = list.find((c) => c.id === answeredId);
        const updated: Conversation = {
          id: answeredId,
          created_at: existing?.created_at ?? res.user_message.created_at,
          title: res.conversation_title,
          updated_at: res.assistant_message.created_at,
        };
        return [updated, ...list.filter((c) => c.id !== answeredId)];
      });
    } catch (err) {
      // Give the question back so it can be edited and sent again.
      setDraft(question);
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setPendingQuestion(null);
      setSending(false);
    }
  }

  const firstName = user.name.split(" ")[0] || user.name;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Backdrop for the mobile drawers */}
      {(navOpen || docsOpen) && (
        <div
          className="fixed inset-0 z-20 bg-ink/40 xl:hidden"
          onClick={() => {
            setNavOpen(false);
            setDocsOpen(false);
          }}
          aria-hidden="true"
        />
      )}

      {/* History */}
      <aside
        aria-label="Chat history"
        className={`fixed inset-y-0 left-0 z-30 w-72 border-r border-line transition-[transform,visibility] lg:static lg:visible lg:translate-x-0 ${
          navOpen ? "visible translate-x-0" : "invisible -translate-x-full"
        }`}
      >
        <Sidebar
          user={user}
          conversations={conversations}
          loading={loadingList}
          activeId={activeId}
          onSelect={(id) => void selectConversation(id)}
          onNew={newChat}
          onDelete={(id) => void deleteChat(id)}
          onSignOut={() => void signOut()}
          onClose={() => setNavOpen(false)}
        />
      </aside>

      {/* Chat */}
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line bg-paper px-3 py-2.5 sm:px-5 xl:hidden">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            aria-label="Open chat history"
            className="rounded-lg p-2 text-ink hover:bg-white lg:hidden"
          >
            <MenuIcon />
          </button>
          <p className="truncate px-2 font-display text-base font-bold">NoobSync KnowledgeBot</p>
          <button
            type="button"
            onClick={() => setDocsOpen(true)}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold hover:bg-white xl:hidden"
          >
            <FolderIcon size={18} />
            Documents
            {docs.documents.length > 0 && (
              <span className="rounded-full bg-pine px-2 py-0.5 text-xs text-white">
                {docs.documents.length}
              </span>
            )}
          </button>
        </div>

        <ChatWindow
          firstName={firstName}
          messages={messages}
          loading={loadingMessages}
          sending={sending}
          pendingQuestion={pendingQuestion}
          onSuggest={(q) => void send(q)}
        />

        {error && (
          <div
            role="alert"
            className="mx-4 mb-2 flex items-start gap-2 rounded-lg border border-rust/30 bg-rust-soft px-4 py-3 text-sm text-rust sm:mx-8"
          >
            <AlertIcon size={18} className="mt-0.5 shrink-0" />
            <p className="flex-1">{error}</p>
            <button
              type="button"
              onClick={() => setError(null)}
              className="font-semibold underline underline-offset-2"
            >
              Dismiss
            </button>
          </div>
        )}

        <Composer
          value={draft}
          onChange={(v) => {
            setDraft(v);
            if (error) setError(null);
          }}
          onSend={() => void send(draft)}
          disabled={sending}
          focusSignal={activeId ?? "new"}
        />
      </main>

      {/* Documents */}
      <aside
        aria-label="Your documents"
        className={`fixed inset-y-0 right-0 z-30 w-80 border-l border-line bg-panel transition-[transform,visibility] xl:static xl:visible xl:translate-x-0 ${
          docsOpen ? "visible translate-x-0" : "invisible translate-x-full"
        }`}
      >
        <DocumentsPanel docs={docs} onClose={() => setDocsOpen(false)} />
      </aside>
    </div>
  );
}
