import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { WorkspaceProvider } from "@/lib/workspace";
import "./index.css";
import App from "./App";
import { SessionProvider } from "@/lib/session";
const client = new QueryClient({
  defaultOptions: {
    queries: { refetchOnWindowFocus: false, retry: false },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem
      disableTransitionOnChange
    >
      <QueryClientProvider client={client}>
        <WorkspaceProvider>
          <TooltipProvider>
            <SessionProvider>
              <App />
            </SessionProvider>
            <Toaster position="bottom-right" richColors />
          </TooltipProvider>
        </WorkspaceProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
