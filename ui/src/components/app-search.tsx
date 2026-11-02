import { useRef } from "react";
import { SearchIcon } from "lucide-react";
import { useKeypress } from "@/hooks/use-keypress";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { useSidebar } from "@/components/ui/sidebar";
import { navigate } from "@/lib/router";
export function AppSearch() {
  const ref = useRef<HTMLInputElement>(null);
  const { setOpen, setOpenMobile, isMobile } = useSidebar();
  useKeypress({
    combo: ["meta+k", "ctrl+k"],
    callback: () => {
      if (isMobile) setOpenMobile(true);
      else setOpen(true);
      requestAnimationFrame(() => ref.current?.focus());
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        navigate("followups", { q: ref.current?.value || "" });
        if (isMobile) setOpenMobile(false);
      }}
    >
      <InputGroup>
        <InputGroupAddon align="inline-start">
          <SearchIcon />
        </InputGroupAddon>
        <InputGroupInput
          ref={ref}
          aria-label="Search clinic records"
          name="q"
          placeholder="Search..."
          type="search"
        />
        <InputGroupAddon align="inline-end">
          <KbdGroup>
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </KbdGroup>
        </InputGroupAddon>
      </InputGroup>
    </form>
  );
}
