import { createSignal, createMemo, createEffect, type Accessor } from "solid-js";

export type Pager<T> = {
  page: Accessor<number>;
  setPage: (n: number) => void;
  totalPages: Accessor<number>;
  pageItems: Accessor<T[]>;
  total: Accessor<number>;
  pageSize: number;
};

/**
 * Client-side pagination over a reactive list. Resets to page 0 whenever the
 * underlying list shrinks below the current page (e.g. after a filter change).
 */
export function createPager<T>(items: Accessor<T[]>, pageSize = 24): Pager<T> {
  const [page, setPage] = createSignal(0);
  const total = createMemo(() => items().length);
  const totalPages = createMemo(() => Math.max(1, Math.ceil(total() / pageSize)));
  createEffect(() => {
    if (page() >= totalPages()) setPage(0);
  });
  const pageItems = createMemo(() => {
    const start = page() * pageSize;
    return items().slice(start, start + pageSize);
  });
  return { page, setPage, totalPages, pageItems, total, pageSize };
}
