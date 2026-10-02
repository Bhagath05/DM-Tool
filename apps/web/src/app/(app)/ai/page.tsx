"use client";

/**
 * Marketing Brain — the AI-native workspace.
 *
 * A first-class workspace (conversation rail + thread + composer), NOT a chatbot
 * sidebar. It drives the existing Phase 2–4B agent API: READ tools run inline;
 * consequential actions are only PROPOSED (they create a PENDING approval and
 * never execute). Every answer renders through the shared generative-UI
 * primitives. Nothing is fabricated — the UI shows only what the API returns,
 * and a proposed action is always surfaced as "approval required", never done.
 */

import { Brain, Plus, Send, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AgentAnswer, HistoricalAssistantAnswer } from "@/components/brain/agent-response";
import { SectionHeading } from "@/components/ui/section-heading";
import { SkeletonLines } from "@/components/ui/skeleton";
import { api, type AgentConversation, type AgentResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

const SUGGESTIONS = [
  "Why did my ads perform badly this week?",
  "What should I do next?",
  "Which audience converts best for me?",
  "Summarize what changed in my marketing this week.",
];

type ThreadItem =
  | { kind: "user"; id: string; content: string }
  | { kind: "assistant"; id: string; response: AgentResponse }
  | { kind: "history-user"; id: string; content: string }
  | { kind: "history-assistant"; id: string; content: string; meta: Record<string, unknown> };

export default function MarketingBrainPage() {
  const [conversations, setConversations] = useState<AgentConversation[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const seededRef = useRef(false);

  // Load the conversation list once.
  useEffect(() => {
    api.agent
      .listConversations()
      .then((r) => setConversations(r.items))
      .catch(() => setConversations([]));
  }, []);

  const scrollToEnd = useCallback(() => {
    requestAnimationFrame(() => {
      try {
        threadEndRef.current?.scrollIntoView?.({ block: "end" });
      } catch {
        /* scrollIntoView is unimplemented in jsdom / older browsers */
      }
    });
  }, []);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || sending) return;
      setError(null);
      setSending(true);
      setInput("");
      const userItem: ThreadItem = { kind: "user", id: `u-${Date.now()}`, content };
      setThread((t) => [...t, userItem]);
      scrollToEnd();
      try {
        let convoId = activeId;
        if (!convoId) {
          const convo = await api.agent.createConversation(content.slice(0, 60));
          convoId = convo.id;
          setActiveId(convoId);
          setConversations((c) => [convo, ...(c ?? [])]);
        }
        const response = await api.agent.sendMessage(convoId, content);
        setThread((t) => [...t, { kind: "assistant", id: response.message_id, response }]);
        scrollToEnd();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "The Brain couldn't answer just now. Please try again.",
        );
      } finally {
        setSending(false);
      }
    },
    [activeId, sending, scrollToEnd],
  );

  // Auto-seed from a ?q= handoff (e.g. the command palette "Ask the Brain").
  useEffect(() => {
    if (seededRef.current || conversations === null) return;
    seededRef.current = true;
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q && q.trim()) void send(q);
  }, [conversations, send]);

  const openConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setRailOpen(false);
    setError(null);
    setThread([]);
    try {
      const r = await api.agent.listMessages(id);
      setThread(
        r.items.map((m) =>
          m.role === "user"
            ? { kind: "history-user", id: m.id, content: m.content }
            : { kind: "history-assistant", id: m.id, content: m.content, meta: m.meta },
        ),
      );
    } catch {
      setError("Couldn't load that conversation.");
    }
  }, []);

  const startNew = useCallback(() => {
    setActiveId(null);
    setThread([]);
    setError(null);
    setInput("");
    setRailOpen(false);
  }, []);

  const empty = thread.length === 0;

  return (
    <div className="mx-auto flex h-full max-w-6xl gap-0 lg:gap-6" data-testid="brain-workspace">
      {/* Conversation rail — quiet, collapsible. */}
      <aside
        className={cn(
          "w-64 shrink-0 flex-col border-r border-border pr-4 lg:flex",
          railOpen ? "flex" : "hidden",
        )}
        data-testid="brain-rail"
        aria-label="Conversations"
      >
        <button
          type="button"
          onClick={startNew}
          data-testid="brain-new"
          className="mb-3 inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
        >
          <Plus className="h-4 w-4" />
          New conversation
        </button>
        <nav className="scrollbar-clean flex-1 overflow-y-auto">
          {conversations === null ? (
            <SkeletonLines lines={4} />
          ) : conversations.length === 0 ? (
            <p className="px-1 text-xs text-muted-foreground">No conversations yet.</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {conversations.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => openConversation(c.id)}
                    className={cn(
                      "w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                      c.id === activeId
                        ? "bg-muted font-medium text-foreground"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {c.title || "Untitled"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </aside>

      {/* Main workspace. */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-start justify-between gap-3">
          <SectionHeading
            eyebrow="Marketing Brain"
            heading="Ask anything about your marketing"
            description="I understand your business, your data, and what's worked. I can look things up and prepare actions — but I only act after you approve."
          />
          <button
            type="button"
            onClick={() => setRailOpen((o) => !o)}
            className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground lg:hidden"
            aria-expanded={railOpen}
          >
            <Brain className="h-4 w-4" />
            Chats
          </button>
        </div>

        {/* Thread. */}
        <div
          className="scrollbar-clean mt-5 flex-1 overflow-y-auto"
          role="log"
          aria-live="polite"
          aria-label="Conversation with the Marketing Brain"
          data-testid="brain-thread"
        >
          {empty ? (
            <div className="flex flex-col items-start gap-4 py-6" data-testid="brain-empty">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Sparkles className="h-4 w-4 text-ai" />
                Try asking:
              </div>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    data-testid="brain-suggestion"
                    className="w-fit rounded-lg border border-border px-3 py-2 text-left text-sm text-foreground transition-colors hover:border-ai-border hover:bg-ai-soft/40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-5 pb-4">
              {thread.map((item) => (
                <ThreadRow key={item.id} item={item} />
              ))}
              {sending && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="brain-thinking">
                  <Sparkles className="h-4 w-4 animate-pulse text-ai motion-reduce:animate-none" />
                  The Brain is thinking…
                </div>
              )}
              <div ref={threadEndRef} />
            </div>
          )}
        </div>

        {error && (
          <p className="mt-2 text-sm text-bad" data-testid="brain-error">
            {error}
          </p>
        )}

        {/* Composer. */}
        <form
          className="mt-3 flex items-end gap-2 border-t border-border pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={1}
            placeholder="Ask the Marketing Brain…"
            aria-label="Ask the Marketing Brain"
            data-testid="brain-input"
            className="scrollbar-clean max-h-40 min-h-[2.5rem] w-full resize-none rounded-lg border border-border bg-background p-2.5 text-sm outline-none focus:border-ai-border"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            data-testid="brain-send"
            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg bg-ai px-4 text-sm font-medium text-ai-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            <span className="hidden sm:inline">Ask</span>
          </button>
        </form>
      </div>
    </div>
  );
}

function ThreadRow({ item }: { item: ThreadItem }) {
  if (item.kind === "user" || item.kind === "history-user") {
    return (
      <div className="flex justify-end" data-testid="brain-user-message">
        <div className="max-w-[85%] rounded-xl rounded-br-sm bg-foreground px-4 py-2.5 text-sm text-background">
          {item.content}
        </div>
      </div>
    );
  }
  if (item.kind === "assistant") {
    return (
      <div className="max-w-[92%]">
        <AgentAnswer response={item.response} />
      </div>
    );
  }
  return (
    <div className="max-w-[92%]">
      <HistoricalAssistantAnswer content={item.content} meta={item.meta} />
    </div>
  );
}
