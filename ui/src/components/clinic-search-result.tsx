import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHead,
  TableRow,
} from "@/components/ui/table";
import type { SearchAnswer } from "@/lib/ai-search";

/** Shared result presentation for sidebar search and the floating agent. */
export function ClinicSearchResult({ answer }: { answer: SearchAnswer }) {
  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
        {answer.explanation}
      </p>
      {answer.result.rows.length ? (
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                {answer.result.columns.map((column, i) => (
                  <TableHead key={i} className="whitespace-nowrap">
                    {column}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {answer.result.rows.map((row, i) => (
                <TableRow key={i}>
                  {row.map((cell, j) => (
                    <TableCell
                      key={j}
                      className="max-w-80 whitespace-pre-wrap break-words"
                    >
                      {cell ?? "—"}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="rounded-lg border border-dashed p-4 text-muted-foreground">
          No matching records. Try another name, date range, or follow-up type.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        {answer.result.row_count}{" "}
        {answer.result.row_count === 1 ? "result" : "results"}
        {answer.result.truncated
          ? " · Results truncated; narrow your question for more detail."
          : ""}
      </p>
      <details className="text-xs text-muted-foreground">
        <summary className="w-fit cursor-pointer">Query details</summary>
        <pre className="mt-2 overflow-auto rounded-lg bg-muted p-3">
          {answer.sql}
        </pre>
      </details>
    </div>
  );
}
