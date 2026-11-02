import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { useRecordPermissions } from "@/lib/session";
import { titleCase } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

interface ImportResult {
  saved: boolean;
  counts: Record<string, number>;
  rejections: { kind: string; record_id: string; reason: string }[];
}

export function ImportPage() {
  const { api, sample } = useWorkspace();
  const { manage } = useRecordPermissions();
  const cache = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  async function importFile() {
    if (!file || !manage || sample) return;
    setPending(true);
    setResult(null);
    setError("");
    try {
      let body: unknown;
      try {
        body = JSON.parse(await file.text());
      } catch {
        throw new Error(
          "This file could not be read as JSON. Choose a valid JSON data file and try again.",
        );
      }
      const next = await api<ImportResult>("import", { method: "POST", body });
      setResult(next);
      await cache.invalidateQueries();
    } catch (failure) {
      if (
        failure instanceof ApiError &&
        failure.status === 422 &&
        failure.payload &&
        typeof failure.payload === "object" &&
        "rejections" in failure.payload &&
        Array.isArray(failure.payload.rejections)
      ) {
        setResult(failure.payload as ImportResult);
      } else {
        setError((failure as Error).message);
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Import data</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Add a complete set of synthetic clinic records.
        </p>
      </div>
      <Card className="max-w-3xl dark:bg-transparent">
        <CardHeader>
          <CardTitle>Import a JSON file</CardTitle>
          <CardDescription>
            Every record is validated before saving. If any record is rejected,
            nothing in the file is saved. Existing IDs and staff emails are
            rejected.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {!manage && (
            <p role="status" className="text-sm text-muted-foreground">
              Only a manager can import records.
            </p>
          )}
          {sample && (
            <p role="status" className="text-sm text-muted-foreground">
              Connect your workspace and sign in as a manager to import records.
            </p>
          )}
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void importFile();
            }}
          >
            <div className="space-y-2">
              <label htmlFor="import-file" className="text-sm font-medium">
                Synthetic data file
              </label>
              <Input
                id="import-file"
                type="file"
                accept=".json,application/json"
                required
                disabled={pending || sample || !manage}
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setResult(null);
                  setError("");
                }}
              />
            </div>
            <Button
              type="submit"
              disabled={!file || pending || sample || !manage}
            >
              {pending ? <Loader2 className="animate-spin" /> : <FileUp />}
              {pending ? "Validating and importing…" : "Validate and import"}
            </Button>
          </form>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {result && (
            <div className="space-y-4 border-t pt-4">
              <p
                role={result.saved ? "status" : "alert"}
                className="text-sm font-medium"
              >
                {result.saved
                  ? "Import complete. All records were saved."
                  : `Import rejected: ${result.rejections.length} problems. Nothing was saved.`}
              </p>
              {result.saved ? (
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                  {Object.entries(result.counts).map(([kind, count]) => (
                    <div key={kind}>
                      <dt className="text-muted-foreground">
                        {titleCase(kind)}
                      </dt>
                      <dd className="mt-1 font-medium tabular-nums">{count}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <div className="max-h-96 overflow-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Record</TableHead>
                        <TableHead>Problem</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.rejections.map((rejection, index) => (
                        <TableRow key={index}>
                          <TableCell className="align-top">
                            {titleCase(rejection.kind)} {rejection.record_id}
                          </TableCell>
                          <TableCell className="whitespace-normal">
                            {rejection.reason}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
