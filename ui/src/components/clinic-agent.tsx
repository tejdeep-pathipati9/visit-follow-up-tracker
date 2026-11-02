import { useEffect, useRef, useState } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import {
  ArrowUp,
  ArrowUpRight,
  LayoutDashboard,
  Loader2,
  Maximize2,
  Minimize2,
  Minus,
  MousePointer2,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogClose,
  DialogDescription,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ClinicSearchResult } from "@/components/clinic-search-result";
import { clinicQuestions, type SearchAnswer } from "@/lib/ai-search";
import { useWorkspace } from "@/lib/workspace";
import { useSession } from "@/lib/session";
import { navigate } from "@/lib/router";
import { formatDate } from "@/lib/types";
import { cn } from "@/lib/utils";

type Exchange = {
  id: number;
  question: string;
  answer?: SearchAnswer;
  error?: string;
};

/** Each question uses the existing read-only, role-scoped search endpoint. */
export function ClinicAgent() {
  const { sample, asOf } = useWorkspace();
  const { user } = useSession();
  // Never carry responses between identities, data sources, or assessment dates.
  return (
    <AgentPanel key={`${user?.staff_id || "preview"}:${sample}:${asOf}`} />
  );
}

function AgentPanel() {
  const { api, sample, setSample, asOf } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState(false);
  const active = useRef<AbortController | null>(null);
  const serial = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    if (open)
      bottom.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
  }, [open, exchanges, pending]);

  function newChat() {
    active.current?.abort();
    active.current = null;
    setPending(false);
    setExchanges([]);
    setQuestion("");
    input.current?.focus();
  }
  async function ask(raw: string) {
    const text = raw.trim();
    if (!text || text.length > 1000 || active.current) return;
    const controller = new AbortController();
    active.current = controller;
    const id = ++serial.current;
    setQuestion("");
    setPending(true);
    setExchanges((old) => [...old, { id, question: text }]);
    try {
      const answer = await api<SearchAnswer>("ask", {
        method: "POST",
        body: { question: text, as_of_date: asOf },
        signal: controller.signal,
      });
      if (!controller.signal.aborted)
        setExchanges((old) =>
          old.map((item) => (item.id === id ? { ...item, answer } : item)),
        );
    } catch (error) {
      if (!controller.signal.aborted)
        setExchanges((old) =>
          old.map((item) =>
            item.id === id
              ? { ...item, error: (error as Error).message }
              : item,
          ),
        );
    } finally {
      if (active.current === controller) {
        active.current = null;
        setPending(false);
      }
    }
  }
  function showDashboard() {
    active.current?.abort();
    setOpen(false);
    setSample(true);
    navigate("overview");
  }
  return (
    <Dialog open={open} onOpenChange={setOpen} modal={false}>
      <DialogTrigger asChild>
        <Button
          variant="secondary"
          aria-label="Open clinic agent"
          className="fixed right-4 bottom-4 z-40 h-11 gap-2 rounded-xl border bg-background px-4 text-sm shadow-lg hover:bg-muted print:hidden md:right-6 md:bottom-5"
        >
          <MousePointer2 className="size-4 -rotate-12" />
          Agent
          {pending && (
            <>
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
              <span className="sr-only">Searching</span>
            </>
          )}
        </Button>
      </DialogTrigger>
      <DialogPortal>
        <DialogPrimitive.Content
          aria-describedby="clinic-agent-description"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            input.current?.focus();
          }}
          onInteractOutside={(event) => event.preventDefault()}
          className={cn(
            "fixed right-3 bottom-18 z-[45] flex max-h-[calc(100dvh-6rem)] w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl border bg-background text-foreground shadow-[0_24px_80px_-24px_rgb(0_0_0_/_0.4)] outline-none print:hidden md:right-6 md:bottom-19",
            expanded
              ? "h-[calc(100dvh-7rem)] sm:w-[min(800px,calc(100vw-3rem))]"
              : "h-[min(660px,calc(100dvh-6rem))] sm:w-[460px]",
          )}
        >
          <div className="flex shrink-0 items-center gap-2 border-b bg-muted/20 px-4 py-3">
            <DialogTitle className="mr-auto text-sm font-medium">
              {exchanges.length ? "Clinic agent" : "New chat"}
            </DialogTitle>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="New chat"
              onClick={newChat}
            >
              <Plus className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Open AI Search page"
              onClick={() => {
                setOpen(false);
                navigate("ask");
              }}
            >
              <ArrowUpRight className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Minimize agent"
              onClick={() => setOpen(false)}
            >
              <Minus className="size-4" />
            </Button>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label={expanded ? "Restore agent size" : "Expand agent"}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <Minimize2 className="size-4" />
              ) : (
                <Maximize2 className="size-4" />
              )}
            </Button>
            <DialogClose asChild>
              <Button size="icon-sm" variant="ghost" aria-label="Close agent">
                <X className="size-4" />
              </Button>
            </DialogClose>
          </div>
          <DialogDescription
            id="clinic-agent-description"
            className="shrink-0 border-b px-4 py-2 text-[11px]"
          >
            {sample ? "Sample workspace" : "Clinic workspace"} ·{" "}
            {formatDate(asOf)} · Read-only search
          </DialogDescription>
          <div
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5"
            aria-busy={pending}
          >
            {!exchanges.length ? (
              <div className="flex min-h-full flex-col justify-center gap-5 py-3">
                <div className="space-y-3 text-center">
                  <span className="mx-auto flex size-11 items-center justify-center rounded-2xl border bg-muted/40">
                    <Sparkles className="size-5 text-muted-foreground" />
                  </span>
                  <h3 className="text-lg font-semibold tracking-tight">
                    A little help with the follow-through.
                  </h3>
                  <p className="mx-auto max-w-72 text-sm leading-relaxed text-muted-foreground">
                    Find what needs attention, check a patient’s next step, or
                    explore your clinic’s workload.
                  </p>
                </div>
                <div className="space-y-2">
                  {clinicQuestions.slice(0, 2).map((text) => (
                    <button
                      key={text}
                      className="flex w-full items-center justify-between gap-4 rounded-xl border px-3 py-3 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                      onClick={() => void ask(text)}
                    >
                      {text}
                      <ArrowUpRight className="size-3.5 shrink-0" />
                    </button>
                  ))}
                  <button
                    onClick={showDashboard}
                    className="flex w-full items-center gap-2 rounded-xl border border-dashed px-3 py-3 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <LayoutDashboard className="size-4" />
                    {sample
                      ? "View sample dashboard"
                      : "Explore a sample dashboard"}
                    <span className="ml-auto rounded border px-1.5 py-0.5 text-[10px]">
                      DEMO
                    </span>
                  </button>
                </div>
              </div>
            ) : (
              <div
                className="space-y-6"
                role="log"
                aria-label="Agent conversation"
                aria-live="polite"
              >
                {exchanges.map((item) => (
                  <section key={item.id} className="min-w-0 space-y-4">
                    <p className="ml-6 rounded-xl bg-muted px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words">
                      {item.question}
                    </p>
                    {item.answer && (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-xs font-medium">
                          <Sparkles className="size-3.5" />
                          Clinic agent
                        </div>
                        <ClinicSearchResult answer={item.answer} />
                      </div>
                    )}
                    {item.error && (
                      <div
                        role="alert"
                        className="rounded-xl border p-3 text-sm"
                      >
                        <p className="mb-1 font-medium">
                          We couldn’t answer that question
                        </p>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          {item.error}
                        </p>
                        {!sample && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            disabled={pending}
                            onClick={() => void ask(item.question)}
                          >
                            Try again
                          </Button>
                        )}
                      </div>
                    )}
                  </section>
                ))}
                {pending && (
                  <p
                    role="status"
                    className="flex items-center gap-2 text-xs text-muted-foreground"
                  >
                    <Loader2 className="size-3.5 animate-spin" />
                    Searching your permitted clinic records…
                  </p>
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
          <div className="shrink-0 p-3 pt-0">
            {sample && (
              <p className="mb-2 px-1 text-[11px] leading-relaxed text-muted-foreground">
                Sample dashboard only.{" "}
                <button
                  className="underline underline-offset-2"
                  onClick={() => setSample(false)}
                >
                  Connect your workspace
                </button>{" "}
                to ask AI questions.
              </p>
            )}
            <form
              className="rounded-xl border bg-muted/30 p-2 focus-within:ring-2 focus-within:ring-ring/40"
              onSubmit={(event) => {
                event.preventDefault();
                void ask(question);
              }}
            >
              <Textarea
                ref={input}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                maxLength={1000}
                aria-label="Ask clinic agent"
                placeholder="Ask about patients or follow-ups…"
                className="min-h-16 max-h-32 resize-none border-0 bg-transparent px-1 py-1.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing
                  ) {
                    event.preventDefault();
                    void ask(question);
                  }
                }}
              />
              <div className="mt-1 flex items-center justify-between gap-2 pl-1">
                <span className="text-[10px] text-muted-foreground">
                  Read only · Shift + Enter for a new line
                </span>
                <Button
                  size="icon-sm"
                  type="submit"
                  aria-label="Send question"
                  disabled={pending || !question.trim()}
                  className="rounded-full"
                >
                  {pending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <ArrowUp className="size-4" />
                  )}
                </Button>
              </div>
            </form>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
