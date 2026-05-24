/* @refresh reload */
import { render } from "solid-js/web";
import { lazy } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";

import Layout from "./components/Layout";
import "./styles.css";

const Dashboard  = lazy(() => import("./routes/Dashboard"));
const Inventory  = lazy(() => import("./routes/Inventory"));
const PrimeParts = lazy(() => import("./routes/PrimeParts"));
const Sets       = lazy(() => import("./routes/Sets"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

render(
  () => (
    <QueryClientProvider client={queryClient}>
      <Router root={Layout}>
        <Route path="/"            component={Dashboard} />
        <Route path="/inventory"   component={Inventory} />
        <Route path="/prime-parts" component={PrimeParts} />
        <Route path="/sets"        component={Sets} />
      </Router>
    </QueryClientProvider>
  ),
  root,
);
