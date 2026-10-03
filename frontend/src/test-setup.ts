/**
 * jsdom has no IntersectionObserver; motion's in-view animations need one.
 * This stand-in reports every element as visible straight away, which is
 * also what a user scrolled to it would see.
 */
class VisibleIntersectionObserver {
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.callback(
      [{ isIntersecting: true, target, intersectionRatio: 1 } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver =
    VisibleIntersectionObserver as unknown as typeof IntersectionObserver;
}
