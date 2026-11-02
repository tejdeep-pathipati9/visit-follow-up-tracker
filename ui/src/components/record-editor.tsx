import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useApi, useWorkspace } from "@/lib/workspace";
import { useRecordPermissions } from "@/lib/session";
import type { Page, Options } from "@/lib/types";
export type Resource =
  "patients" | "staff" | "episodes" | "visits" | "followups";
type Field = {
  name: string;
  label: string;
  required?: boolean;
  type?: "date" | "email" | "textarea";
  reference?: Resource;
  options?: string[];
  createOnly?: boolean;
  editOnly?: boolean;
};
export const RESOURCE_CONFIG: Record<
  Resource,
  { title: string; singular: string; id: string; fields: Field[] }
> = {
  patients: {
    title: "Patients",
    singular: "patient",
    id: "patient_id",
    fields: [
      { name: "patient_id", label: "Patient ID", createOnly: true },
      { name: "name", label: "Name", required: true },
      { name: "phone", label: "Phone" },
      { name: "email", label: "Email", type: "email" },
    ],
  },
  staff: {
    title: "Staff",
    singular: "staff member",
    id: "staff_id",
    fields: [
      { name: "staff_id", label: "Staff ID", createOnly: true },
      { name: "name", label: "Name", required: true },
      { name: "role", label: "Role", required: true },
      { name: "email", label: "Sign-in email", type: "email" },
    ],
  },
  episodes: {
    title: "Episodes",
    singular: "episode",
    id: "episode_id",
    fields: [
      { name: "episode_id", label: "Episode ID", createOnly: true },
      {
        name: "patient_id",
        label: "Patient",
        required: true,
        reference: "patients",
        createOnly: true,
      },
      { name: "description", label: "Description", required: true },
      { name: "opened_at", label: "Opened date", type: "date", required: true },
      { name: "closed_at", label: "Closed date", type: "date" },
    ],
  },
  visits: {
    title: "Visits",
    singular: "visit",
    id: "visit_id",
    fields: [
      { name: "visit_id", label: "Visit ID", createOnly: true },
      {
        name: "episode_id",
        label: "Episode",
        reference: "episodes",
        required: true,
        createOnly: true,
      },
      { name: "visit_date", label: "Visit date", type: "date", required: true },
      {
        name: "staff_id",
        label: "Seen by",
        reference: "staff",
        required: true,
      },
      { name: "notes", label: "Visit notes", type: "textarea" },
    ],
  },
  followups: {
    title: "Follow-ups",
    singular: "follow-up",
    id: "followup_id",
    fields: [
      { name: "followup_id", label: "Follow-up ID", createOnly: true },
      {
        name: "visit_id",
        label: "Visit",
        reference: "visits",
        required: true,
        createOnly: true,
      },
      {
        name: "action_type",
        label: "Follow-up type",
        options: ["lab", "referral", "recheck"],
        required: true,
      },
      { name: "due_date", label: "Scheduled date (optional)", type: "date" },
      {
        name: "assigned_staff_id",
        label: "Assigned staff",
        reference: "staff",
        required: true,
      },
      {
        name: "status",
        label: "Status",
        options: ["open", "done", "closed"],
        required: true,
        editOnly: true,
      },
      {
        name: "notes",
        label: "Follow-up notes / closure reason",
        type: "textarea",
      },
    ],
  },
};
function EditorField({
  spec,
  value,
  onChange,
  disabled = false,
}: {
  disabled?: boolean;
  spec: Field;
  value: string;
  onChange: (v: string) => void;
}) {
  const query = useApi<Page<Record<string, unknown>>>(
    spec.reference || "staff",
    { limit: 1000 },
    Boolean(spec.reference) && spec.reference !== "staff",
  );
  const staffOptions = useApi<Options>(
    "options",
    {},
    spec.reference === "staff",
  );
  const options =
    (spec.reference === "staff"
      ? staffOptions.data?.staff?.map((staff) => ({
          value: staff.staff_id,
          label: `${staff.staff_id} · ${staff.name}`,
        }))
      : undefined) ||
    spec.options?.map((v) => ({
      value: v,
      label: v[0].toUpperCase() + v.slice(1),
    })) ||
    query.data?.items.map((r) => ({
      value: String(r[RESOURCE_CONFIG[spec.reference!].id]),
      label: `${r[RESOURCE_CONFIG[spec.reference!].id]} · ${r.name || r.patient_name || r.description || r.visit_date}`,
    })) ||
    [];
  const id = `editor-${spec.name}`;
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="text-sm font-medium">
        {spec.label}
        {spec.required && <span className="text-muted-foreground"> *</span>}
      </label>
      {spec.options || spec.reference ? (
        <>
          <Select
            disabled={disabled}
            required={spec.required}
            value={value || "__none"}
            onValueChange={(v) => onChange(v === "__none" ? "" : v)}
          >
            <SelectTrigger id={id} className="w-full">
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none">
                {spec.required ? "Choose…" : "None"}
              </SelectItem>
              {options.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {query.error && (
            <p className="text-xs text-destructive">{query.error.message}</p>
          )}
        </>
      ) : spec.type === "textarea" ? (
        <Textarea
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Input
          id={id}
          type={spec.type || "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required={spec.required}
          placeholder={
            spec.name.endsWith("_id")
              ? "Leave blank to generate an ID"
              : undefined
          }
        />
      )}
    </div>
  );
}
export function RecordEditor({
  resource,
  open,
  onClose,
  record,
  prefill = {},
}: {
  resource: Resource;
  open: boolean;
  onClose: () => void;
  record?: Record<string, unknown>;
  prefill?: Record<string, string>;
}) {
  const { api, sample } = useWorkspace();
  const { manage, user } = useRecordPermissions();
  const cache = useQueryClient();
  const config = RESOURCE_CONFIG[resource];
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => {
    if (open)
      setValues(
        Object.fromEntries(
          config.fields.map((f) => [
            f.name,
            String(
              prefill[f.name] ??
                (record
                  ? (record[f.name] ?? "")
                  : !manage &&
                      (f.name === "assigned_staff_id" || f.name === "staff_id")
                    ? (user?.staff_id ?? "")
                    : ""),
            ),
          ]),
        ),
      );
  }, [open, record, resource]); // Prefill is captured when the editor opens.
  const fields = config.fields.filter((f) =>
    record ? !f.createOnly : !f.editOnly,
  );
  const mutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {};
      for (const f of fields) {
        const value = values[f.name]?.trim() || null;
        if (f.required && !value) throw new Error(`${f.label} is required.`);
        if (record) {
          if (value !== (record[f.name] ?? null)) body[f.name] = value;
        } else if (value !== null) body[f.name] = value;
      }
      if (
        resource === "followups" &&
        values.status === "closed" &&
        !values.notes?.trim()
      ) {
        throw new Error("Add a reason in notes before closing a follow-up.");
      }
      if (record && !Object.keys(body).length)
        throw new Error("No changes to save.");
      return api(
        `${resource}${record ? "/" + encodeURIComponent(String(record[config.id])) : ""}`,
        { method: record ? "PATCH" : "POST", body },
      );
    },
    onSuccess: async () => {
      await cache.invalidateQueries();
      toast.success(record ? "Record updated." : "Record created.");
      onClose();
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v && !mutation.isPending) onClose();
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {record ? "Edit" : "New"} {config.singular}
          </DialogTitle>
          <DialogDescription>
            {sample
              ? "Connect your workspace to create or edit records. Sample completion actions are available in the worklist."
              : "Changes are saved to your clinic workspace. Use synthetic records only."}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          {fields.map((spec) => (
            <EditorField
              key={spec.name}
              spec={spec}
              disabled={!manage && spec.name === "action_type"}
              value={values[spec.name] || ""}
              onChange={(v) => setValues({ ...values, [spec.name]: v })}
            />
          ))}
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                sample ||
                mutation.isPending ||
                (!manage && (resource !== "followups" || !record))
              }
            >
              {mutation.isPending && <Loader2 className="animate-spin" />}
              {record ? "Save changes" : `Create ${config.singular}`}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
