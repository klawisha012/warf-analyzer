/* @refresh reload */
import { render } from "solid-js/web";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";

import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

render(
  () => (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Route path="/" component={App} />
      </Router>
    </QueryClientProvider>
  ),
  root,
);
