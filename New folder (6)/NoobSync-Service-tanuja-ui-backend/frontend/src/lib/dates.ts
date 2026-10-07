import type { Conversation } from "./api";

export const timeLabel = (iso: string): string =>
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const startOfDay = (d: Date): number =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Groups conversations (already sorted newest first) for the history sidebar. */
export function groupByDay(
  conversations: Conversation[],
  now: Date = new Date(),
): { label: string; items: Conversation[] }[] {
  const today = startOfDay(now);
  const DAY = 24 * 60 * 60 * 1000;
  const buckets: { label: string; items: Conversation[] }[] = [
    { label: "Today", items: [] },
    { label: "Yesterday", items: [] },
    { label: "Previous 7 days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const c of conversations) {
    const age = today - startOfDay(new Date(c.updated_at));
    const idx = age < DAY ? 0 : age < 2 * DAY ? 1 : age < 7 * DAY ? 2 : 3;
    buckets[idx].items.push(c);
  }
  return buckets.filter((b) => b.items.length > 0);
}
