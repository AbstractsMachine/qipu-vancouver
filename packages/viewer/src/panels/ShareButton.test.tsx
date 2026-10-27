import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShareButton } from "./ShareButton";

const url = "https://www.qipu.org/en/usa/san-francisco/the-city?year=1938&block=3547-012";

/** The copy finishes after the click's own act() scope, so wrap both to flush the effects it starts. */
async function pressShare(user: ReturnType<typeof userEvent.setup>) {
  await act(async () => {
    await user.click(screen.getByRole("button", { name: "Share" }));
  });
}

function setup() {
  const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
  // user-event installs its own clipboard on setup, so the stub goes on afterwards.
  const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  render(<ShareButton url={url} />);
  return { user, writeText };
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "share");
});

describe("ShareButton", () => {
  it("copies the link and says so for two seconds", async () => {
    const { user, writeText } = setup();
    await pressShare(user);
    expect(writeText).toHaveBeenCalledWith(url);
    expect(screen.getByRole("status")).toHaveTextContent("Link copied");

    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Link copied");
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("falls back to a selected link field when copying fails", async () => {
    const { user, writeText } = setup();
    writeText.mockRejectedValue(new DOMException("denied", "NotAllowedError"));
    await pressShare(user);
    const field = screen.getByRole("textbox", { name: "Link to this view" });
    expect(field).toHaveValue(url);
    expect(field).toHaveAttribute("readonly");
    expect(field).toHaveFocus();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  describe("on a touch device", () => {
    beforeEach(() => {
      vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === "(pointer: coarse)" }));
    });

    it("opens the system share sheet", async () => {
      const share = vi.fn<(data: ShareData) => Promise<void>>().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "share", { value: share, configurable: true });
      const { user, writeText } = setup();
      await pressShare(user);
      expect(share).toHaveBeenCalledWith({ url });
      expect(writeText).not.toHaveBeenCalled();
    });

    it("does nothing more when the reader cancels the sheet", async () => {
      const share = vi.fn().mockRejectedValue(new DOMException("cancelled", "AbortError"));
      Object.defineProperty(navigator, "share", { value: share, configurable: true });
      const { user, writeText } = setup();
      await pressShare(user);
      expect(writeText).not.toHaveBeenCalled();
    });

    it("copies instead when the share sheet fails", async () => {
      const share = vi.fn().mockRejectedValue(new DOMException("blocked", "NotAllowedError"));
      Object.defineProperty(navigator, "share", { value: share, configurable: true });
      const { user, writeText } = setup();
      await pressShare(user);
      expect(writeText).toHaveBeenCalledWith(url);
      expect(screen.getByRole("status")).toHaveTextContent("Link copied");
    });
  });
});
