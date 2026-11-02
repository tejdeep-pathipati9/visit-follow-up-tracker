import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowUp, Loader2, Sparkles } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useWorkspace } from "@/lib/workspace";
import { ClinicSearchResult } from "@/components/clinic-search-result";
import {
  clinicQuestions as examples,
  type SearchAnswer,
} from "@/lib/ai-search";
export function AskPage() {
  const [question, setQuestion] = useState("");
  const { api, asOf, sample } = useWorkspace();
  const mutation = useMutation({
    mutationFn: (q: string) =>
      api<SearchAnswer>("ask", {
        method: "POST",
        body: { question: q, as_of_date: asOf },
      }),
  });
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 py-4 md:py-10">
      <div className="mb-8 space-y-3">
        <span className="inline-flex rounded-lg border bg-background p-2.5">
          <Sparkles className="size-5" />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight">
          Ask your clinic workspace
        </h1>
        <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
          Find patients, visits, and follow-ups in your own words. Answers come
          from your records, and your records stay unchanged.
        </p>
      </div>
      <Card className="dark:bg-transparent">
        <CardHeader>
          <CardTitle className="flex justify-between">
            What would you like to find?
            <Badge variant="outline" className="font-normal">
              Read only
            </Badge>
          </CardTitle>
          <CardDescription>
            {sample
              ? "AI answers are available in the connected workspace. Sample questions below are suggestions."
              : "Use a natural-language question to search your clinic’s records."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (question.trim()) mutation.mutate(question.trim());
            }}
            className="space-y-4"
          >
            <Textarea
              value={question}
              aria-label="Question about clinic records"
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Which patients have overdue lab follow-ups?"
              maxLength={1000}
              required
              className="min-h-28 resize-y bg-background"
            />
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">
                AI never completes, assigns, or changes a follow-up.
              </span>
              <Button disabled={mutation.isPending || !question.trim()}>
                {mutation.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <ArrowUp />
                )}
                Ask
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="flex flex-wrap gap-2">
        {examples.map((q) => (
          <Button
            variant="outline"
            size="sm"
            className="h-auto min-h-8 max-w-full whitespace-normal py-1.5 text-left text-xs text-muted-foreground"
            key={q}
            disabled={mutation.isPending}
            onClick={() => {
              setQuestion(q);
              mutation.mutate(q);
            }}
          >
            {q}
          </Button>
        ))}
      </div>
      {mutation.isPending && (
        <p role="status" className="text-sm text-muted-foreground">
          Searching your clinic’s records…
        </p>
      )}
      {mutation.error && (
        <Card>
          <CardContent className="py-6 text-sm" role="alert">
            <p className="mb-1 font-medium">We couldn’t answer that question</p>
            <p className="text-muted-foreground">{mutation.error.message}</p>
          </CardContent>
        </Card>
      )}
      {mutation.data && (
        <Card>
          <CardHeader>
            <CardTitle>Search results</CardTitle>
          </CardHeader>
          <CardContent>
            <ClinicSearchResult answer={mutation.data} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
