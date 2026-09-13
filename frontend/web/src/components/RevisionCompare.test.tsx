import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  REVISION_REVIEW_COMPARISON,
  type RevisionComparisonView,
} from "../product/governanceReviewFixtures";
import {
  defaultRevisionCompareMode,
  RevisionCompare,
  type RevisionCompareMode,
} from "./RevisionCompare";
import { RestoreRevisionDialog } from "./RestoreRevisionDialog";

afterEach(() => vi.unstubAllGlobals());

function CompareHarness({ comparison = REVISION_REVIEW_COMPARISON, onRestore }: {
  comparison?: RevisionComparisonView;
  onRestore?: (opener: HTMLElement) => void;
}) {
  const [mode, setMode] = useState<RevisionCompareMode>("side-by-side");
  return (
    <RevisionCompare
      comparison={comparison}
      mode={mode}
      onModeChange={setMode}
      onBack={vi.fn()}
      onKeepCurrent={vi.fn()}
      onRestore={onRestore}
    />
  );
}

describe("RevisionCompare and RestoreRevisionDialog", () => {
  it("renders semantic segments, exact counts, and switches view", async () => {
    const user = userEvent.setup();
    const { container } = render(<CompareHarness />);
    expect(container.querySelectorAll("del").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("ins").length).toBeGreaterThan(0);
    expect(screen.getByRole("status")).toHaveTextContent("12 additions");
    await user.click(screen.getByRole("button", { name: "Inline" }));
    expect(screen.getByText("Inline changes")).toBeInTheDocument();
  });

  it("shows plain live snapshots without invented counts or restore", () => {
    const plain: RevisionComparisonView = {
      earlier: REVISION_REVIEW_COMPARISON.earlier,
      later: REVISION_REVIEW_COMPARISON.later,
    };
    const { container } = render(<CompareHarness comparison={plain} />);
    expect(screen.getByRole("status")).toHaveTextContent("No semantic change counts are available");
    expect(container.querySelector("del, ins")).toBeNull();
    expect(screen.queryByRole("button", { name: /restore revision/i })).not.toBeInTheDocument();
  });

  it("uses inline as the default mode for a phone media query", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true } as MediaQueryList));
    expect(defaultRevisionCompareMode()).toBe("inline");
  });

  it("returns focus after cancel and Escape", async () => {
    const user = userEvent.setup();
    function DialogHarness() {
      const [open, setOpen] = useState(false);
      const [opener, setOpener] = useState<HTMLElement | null>(null);
      return (
        <>
          <button type="button" onClick={(event) => { setOpener(event.currentTarget); setOpen(true); }}>
            Open restore
          </button>
          <RestoreRevisionDialog
            open={open}
            revision={REVISION_REVIEW_COMPARISON.earlier}
            newRevisionNumber={8}
            returnFocusTo={opener}
            onConfirm={vi.fn()}
            onCancel={() => setOpen(false)}
          />
        </>
      );
    }
    render(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Open restore" });
    await user.click(opener);
    let dialog = screen.getByRole("dialog", { name: "Restore revision 6?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(opener).toHaveFocus();
    await user.click(opener);
    dialog = screen.getByRole("dialog", { name: "Restore revision 6?" });
    expect(dialog).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("shows pending copy and calls confirm", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn();
    const view = render(
      <RestoreRevisionDialog
        open
        revision={REVISION_REVIEW_COMPARISON.earlier}
        newRevisionNumber={8}
        returnFocusTo={null}
        onConfirm={confirm}
        onCancel={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Restore as revision 8" }));
    expect(confirm).toHaveBeenCalledOnce();
    view.rerender(
      <RestoreRevisionDialog
        open
        pending
        revision={REVISION_REVIEW_COMPARISON.earlier}
        newRevisionNumber={8}
        returnFocusTo={null}
        onConfirm={confirm}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Restoring revision…" })).toBeDisabled();
  });
});
