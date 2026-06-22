import { test, expect } from "@playwright/test";
import { AppShellPage } from "../pages/app-shell.page";

test("app shell renders without a live backend", async ({ page }) => {
  const shell = new AppShellPage(page);
  await shell.goto();

  await expect(page).toHaveTitle("AlecaFrame");
  await expect(shell.sidebar).toBeVisible();
  await expect(shell.brand).toContainText("Frame");
});
