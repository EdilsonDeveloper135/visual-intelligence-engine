import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { applyTheme, useUi } from "./store/ui";
import "./styles/index.css";

applyTheme(useUi.getState().theme);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, retry: (count, err: unknown) => count < 2 && (err as { status?: number })?.status !== 401 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
