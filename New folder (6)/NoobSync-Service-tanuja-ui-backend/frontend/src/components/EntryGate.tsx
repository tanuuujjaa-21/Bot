import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { NAME_MAX, validateName, validatePhone } from "../lib/validation";
import { Spinner } from "./icons";

const fieldBase =
  "w-full border-0 border-b-2 bg-transparent px-1 pb-1 font-display text-2xl font-semibold text-ink " +
  "placeholder:font-normal placeholder:text-mute/50 focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 " +
  "sm:text-3xl";

export default function EntryGate() {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [touched, setTouched] = useState({ name: false, phone: false });
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const nameError = touched.name ? validateName(name) : null;
  const phoneError = touched.phone ? validatePhone(phone) : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched({ name: true, phone: true });
    if (validateName(name) || validatePhone(phone)) return;
    setBusy(true);
    setServerError(null);
    try {
      await signIn(name, phone);
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
      );
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto grid min-h-full max-w-6xl items-center gap-12 px-6 py-10 lg:grid-cols-[1.15fr_0.85fr] lg:gap-20">
      <section>
        <p className="mb-10 flex items-center gap-2.5 font-display text-lg font-bold">
          <span
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-pine text-white"
            aria-hidden="true"
          >
            <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
              <path
                d="M9 22V10l14 12V10"
                stroke="currentColor"
                strokeWidth="3.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          NoobSync KnowledgeBot
        </p>

        <h1 className="max-w-xl text-4xl font-bold leading-[1.08] tracking-tight sm:text-5xl">
          Ask us anything about our services.
        </h1>
        <p className="mt-4 max-w-md text-lg text-mute">
          Tell us who you are first, so our team can follow up if you want a person to take over.
        </p>

        <form onSubmit={onSubmit} noValidate className="mt-10 max-w-xl">
          <div className="space-y-7">
            <div>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-display text-2xl font-semibold text-mute sm:text-3xl" aria-hidden="true">
                  I'm
                </span>
                <div className="min-w-[12rem] flex-1">
                  <label htmlFor="gate-name" className="sr-only">
                    Your name
                  </label>
                  <input
                    id="gate-name"
                    name="name"
                    type="text"
                    autoComplete="name"
                    autoFocus
                    maxLength={NAME_MAX}
                    placeholder="your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onBlur={() => setTouched((t) => ({ ...t, name: true }))}
                    aria-invalid={nameError ? true : undefined}
                    aria-describedby={nameError ? "gate-name-error" : undefined}
                    className={`${fieldBase} ${nameError ? "border-rust" : "border-line focus:border-pine"}`}
                  />
                </div>
              </div>
              {nameError && (
                <p id="gate-name-error" className="mt-2 text-sm text-rust">
                  {nameError}
                </p>
              )}
            </div>

            <div>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-display text-2xl font-semibold text-mute sm:text-3xl" aria-hidden="true">
                  and my number is
                </span>
                <div className="min-w-[12rem] flex-1">
                  <label htmlFor="gate-phone" className="sr-only">
                    Your phone number
                  </label>
                  <input
                    id="gate-phone"
                    name="phone"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    maxLength={20}
                    placeholder="98765 43210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    onBlur={() => setTouched((t) => ({ ...t, phone: true }))}
                    aria-invalid={phoneError ? true : undefined}
                    aria-describedby={phoneError ? "gate-phone-error" : undefined}
                    className={`${fieldBase} ${phoneError ? "border-rust" : "border-line focus:border-pine"}`}
                  />
                </div>
              </div>
              {phoneError && (
                <p id="gate-phone-error" className="mt-2 text-sm text-rust">
                  {phoneError}
                </p>
              )}
            </div>
          </div>

          {serverError && (
            <p
              role="alert"
              className="mt-6 rounded-lg border border-rust/30 bg-rust-soft px-4 py-3 text-sm text-rust"
            >
              {serverError}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-9 inline-flex items-center gap-2 rounded-xl bg-pine px-7 py-3.5 text-base font-semibold text-white transition-colors hover:bg-pine-dark disabled:cursor-wait disabled:opacity-70"
          >
            {busy && <Spinner />}
            {busy ? "Starting your chat" : "Start chatting"}
          </button>
          <p className="mt-4 text-sm text-mute">
            Your name and number are saved with your chats. Nothing else is asked.
          </p>
        </form>
      </section>

      <aside className="hidden lg:block" aria-label="Example conversation">
        <div className="rounded-2xl border border-line bg-panel p-6 shadow-sm">
          <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-pine px-4 py-3 text-white">
            What does WorkflowOps do for a small business?
          </div>
          <div className="mt-4 max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-paper px-4 py-3 leading-relaxed">
            WorkflowOps automates manual business processes across forms, emails, CRMs,
            spreadsheets and approvals, so routine follow-ups stop depending on someone
            remembering.
          </div>
          <div className="ml-auto mt-4 max-w-[85%] rounded-2xl rounded-br-md bg-pine px-4 py-3 text-white">
            Can I ask about my own price list too?
          </div>
          <div className="mt-4 max-w-[92%] rounded-2xl rounded-bl-md border border-line bg-paper px-4 py-3 leading-relaxed">
            Yes. Upload a PDF, Word file, text, Markdown or CSV and I'll answer from it first.
          </div>
        </div>
      </aside>
    </main>
  );
}
