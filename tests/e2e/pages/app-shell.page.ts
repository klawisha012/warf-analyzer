import type { Page, Locator } from "@playwright/test";

/** Page Object for the persistent app shell (sidebar + brand). */
export class AppShellPage {
  readonly page: Page;
  readonly sidebar: Locator;
  readonly brand: Locator;

  constructor(page: Page) {
    this.page = page;
    this.sidebar = page.locator("aside.sidebar");
    this.brand = page.locator(".brand-name");
  }

  /** Stub every backend call so the SPA renders without a live backend. */
  async stubApi(): Promise<void> {
    await this.page.route("**/api/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, wfm_username: "Tenno", items: [], total: 0 }),
      }),
    );
  }

  async goto(): Promise<void> {
    await this.stubApi();
    await this.page.goto("/");
  }
}
