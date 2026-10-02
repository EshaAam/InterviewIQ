import { afterEach, expect, it, vi } from "vitest";
import { saveFile } from "./download";

afterEach(() => vi.useRealTimers());

it("downloads under the given name, then frees the object URL", () => {
  vi.useFakeTimers();
  const create = vi.fn(() => "blob:fake");
  const revoke = vi.fn();
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
  const clicked: HTMLAnchorElement[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked.push(this);
  });

  saveFile(new Blob(["%PDF"]), "report.pdf");

  expect(clicked[0].download).toBe("report.pdf");
  expect(clicked[0].href).toBe("blob:fake");
  expect(document.querySelector("a[download]")).toBeNull(); // removed after the click
  expect(revoke).not.toHaveBeenCalled(); // not yet: the download is still reading it
  vi.advanceTimersByTime(1000);
  expect(revoke).toHaveBeenCalledWith("blob:fake");
});
