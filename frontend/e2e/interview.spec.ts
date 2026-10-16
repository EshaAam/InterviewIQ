import { expect, test, type Page } from "@playwright/test";

/**
 * Locators are by role and label on purpose: `getByLabel("Email")` only works
 * if the field is properly labelled, so these tests fail on the same
 * accessibility mistakes a screen-reader user would hit.
 */

async function signUp(page: Page): Promise<string> {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  // The landing page is public; starting an upload is what asks for an account.
  await page.goto("/");
  await page.getByRole("button", { name: "Upload your resume" }).first().click();
  await expect(page).toHaveURL(/\/login\?next=%2Finterview$/);
  await page.getByRole("button", { name: "No account? Create one." }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/interview$/);
  return email;
}

test("a candidate takes a whole interview and downloads the report", async ({ page }) => {
  await signUp(page);

  // Resume: paste it.
  await page.getByRole("radio", { name: "Paste text" }).click();
  await page
    .getByLabel("Resume text")
    .fill("Backend engineer: python, fastapi and postgresql in production.");
  await page.getByRole("button", { name: "Use this text" }).click();
  await expect(page.getByText("Skills we found")).toBeVisible();

  // Questions are written in a worker; the session page waits for them.
  await page.getByRole("button", { name: "Generate questions" }).click();
  await expect(page).toHaveURL(/\/interview\/[0-9a-f-]{36}$/);
  await page.getByRole("button", { name: "Start interview" }).click();

  // Answer until the app says that was the last one.
  const answer = page.getByLabel("Your answer");
  const finish = page.getByRole("button", { name: "Finish interview" });
  for (let i = 0; i < 10 && !(await finish.isVisible()); i++) {
    await answer.fill("Fundamentals, the tradeoffs, and how I ran it in production.");
    await page.getByRole("button", { name: "Submit answer" }).click();
    // Wait for the submit to *settle*. While it's in flight the old answer is
    // still on screen (disabled), which satisfies a naive "is anything
    // visible?" check — then vanishes. Settled means: the finish card, or a
    // fresh, enabled, empty box for the next question.
    await expect(async () => {
      const done = await finish.isVisible();
      const next =
        (await answer.isVisible()) &&
        (await answer.isEnabled()) &&
        (await answer.inputValue()) === "";
      expect(done || next).toBe(true);
    }).toPass();
  }
  await finish.click();

  // Grading runs in a worker; the page moves to the report when it's done.
  await expect(page).toHaveURL(/\/reports\/[0-9a-f-]{36}$/, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Interview report" })).toBeVisible();
  await expect(page.getByRole("meter").first()).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/^interviewiq-report-.*\.pdf$/);

  // The dashboard lists it.
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "My interviews" })
    .click();
  await expect(page.getByRole("heading", { name: "Recent sessions" })).toBeVisible();
});

test("signing in works from the keyboard alone", async ({ page }) => {
  const email = await signUp(page);
  // Sign out, then back in without touching the mouse.
  await page.getByRole("button", { name: /^Sign out/ }).click();
  await expect(page).toHaveURL(/\/$/); // back to the public landing page
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/login$/);

  await page.keyboard.press("Tab"); // → Email
  await expect(page.getByLabel("Email")).toBeFocused();
  await page.keyboard.type(email);
  await page.keyboard.press("Tab"); // → Password
  await page.keyboard.type("e2e-password-123");
  await page.keyboard.press("Enter"); // submits the form
  await expect(page).toHaveURL(/\/interview$/);
});

test("the landing page is public and the app is not", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Interviews that grade");
  await expect(page).toHaveURL(/\/$/); // no redirect without a token

  // A signed-out visit to an app page goes to sign-in, remembering the page.
  await page.goto("/interview");
  await expect(page).toHaveURL(/\/login\?next=%2Finterview$/);
});

test("an unknown address shows the not-found page", async ({ page }) => {
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
