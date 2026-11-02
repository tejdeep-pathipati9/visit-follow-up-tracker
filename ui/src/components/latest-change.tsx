import { useState } from "react";
import { XIcon, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "@/lib/workspace";
export function LatestChange() {
  const [open, setOpen] = useState(true);
  const { sample, setSample } = useWorkspace();
  if (!open) return null;
  return (
    <div className="group/latest-change relative rounded-lg border bg-background">
      <div className="flex flex-col gap-1.5 px-3 pt-4 pb-1">
        <p className="pr-4 text-xs font-medium">
          {sample ? "Sample workspace" : "Your clinic workspace"}
        </p>
        <span className="text-[11px] leading-relaxed text-muted-foreground">
          {sample
            ? "Explore with synthetic records. Preview changes reset when you reload."
            : "Synthetic data only. Keep every visit’s next step in view."}
        </span>
        <Button
          variant="link"
          size="sm"
          className="w-max px-0 text-xs font-normal"
          onClick={() => setSample(!sample)}
        >
          {sample ? "Connect your data" : "Explore sample data"}
          <ArrowUpRight className="size-3" />
        </Button>
        <Button
          variant="secondary"
          size="icon-sm"
          aria-label="Dismiss workspace note"
          className="absolute top-2 right-2 size-5 opacity-0 group-hover/latest-change:opacity-100 focus-visible:opacity-100"
          onClick={() => setOpen(false)}
        >
          <XIcon className="size-3" />
        </Button>
      </div>
    </div>
  );
}
