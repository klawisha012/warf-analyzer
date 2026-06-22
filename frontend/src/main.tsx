/* @refresh reload */
import { render } from "solid-js/web";
import { lazy } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";
import { persistQueryClient } from "@tanstack/query-persist-client-core";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";

import Layout from "./components/Layout";
import "./styles.css";
import { version as appVersion } from "../package.json";

const Dashboard = lazy(() => import("./routes/Dashboard"));
const Inventory = lazy(() => import("./routes/Inventory"));
const PrimeParts = lazy(() => import("./routes/PrimeParts"));
const Mods = lazy(() => import("./routes/Mods"));
const Arcanes = lazy(() => import("./routes/Arcanes"));
const Sets = lazy(() => import("./routes/Sets"));
const Rivens = lazy(() => import("./routes/Rivens"));
const Fissures = lazy(() => import("./routes/Fissures"));

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: ONE_DAY_MS,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const persister = createSyncStoragePersister({
  storage: window.localStorage,
  key: "alecaframe-query-cache",
});

persistQueryClient({
  queryClient,
  persister,
  maxAge: ONE_DAY_MS,
  buster: appVersion,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.queryKey[0] !== "healthz" && query.state.status === "success",
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

render(
  () => (
    <QueryClientProvider client={queryClient}>
      <Router root={Layout}>
        <Route path="/" component={Dashboard} />
        <Route path="/inventory" component={Inventory} />
        <Route path="/prime-parts" component={PrimeParts} />
        <Route path="/mods" component={Mods} />
        <Route path="/arcanes" component={Arcanes} />
        <Route path="/sets" component={Sets} />
        <Route path="/rivens" component={Rivens} />
        <Route path="/fissures" component={Fissures} />
      </Router>
    </QueryClientProvider>
  ),
  root,
);
