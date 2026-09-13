import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CreateProtocolDialog } from "./CreateProtocolDialog";

function renderDialog(
  overrides: Partial<Parameters<typeof CreateProtocolDialog>[0]> = {},
) {
  const onCreate = overrides.onCreate ?? vi.fn();
  const onClose = overrides.onClose ?? vi.fn();
  const result = render(
    <CreateProtocolDialog
      open
      organizationName="Northstar Clinical Research"
      organizationRole="owner"
      pending={false}
      error={null}
      {...overrides}
      onCreate={onCreate}
      onClose={onClose}
    />,
  );
  return { ...result, onCreate, onClose };
}

describe("CreateProtocolDialog", () => {
  it("moves focus to the protocol title field when it opens", async () => {
    renderDialog();

    await waitFor(() =>
      expect(screen.getByLabelText("Protocol title")).toHaveFocus(),
    );
    expect(
      screen.getByRole("dialog", { name: "Create a protocol workspace" }),
    ).toHaveAttribute("aria-modal", "true");
  });

  it("shows the organization context without a selector", () => {
    renderDialog();

    expect(screen.getByText("Northstar Clinical Research")).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the opener", async () => {
    const user = userEvent.setup();
    const opener = document.createElement("button");
    document.body.append(opener);
    const onClose = vi.fn();

    const { rerender } = renderDialog({ onClose, returnFocusTo: opener });
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();

    rerender(
      <CreateProtocolDialog
        open={false}
        organizationName="Northstar Clinical Research"
        organizationRole="owner"
        pending={false}
        error={null}
        returnFocusTo={opener}
        onCreate={vi.fn()}
        onClose={onClose}
      />,
    );

    await waitFor(() => expect(opener).toHaveFocus());
    opener.remove();
  });

  it("rejects a blank title without calling onCreate", async () => {
    const user = userEvent.setup();
    const { onCreate } = renderDialog();

    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(
      await screen.findByText("Enter a protocol title."),
    ).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("rejects a title over 200 characters", async () => {
    const user = userEvent.setup();
    const { onCreate } = renderDialog();

    await user.type(screen.getByLabelText("Protocol title"), "x".repeat(201));
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(
      await screen.findByText(
        "Protocol titles must be 200 characters or fewer.",
      ),
    ).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("shows the character counter only near the limit", async () => {
    const user = userEvent.setup();
    renderDialog();
    const field = screen.getByLabelText("Protocol title");

    await user.type(field, "AURORA-301");
    expect(screen.queryByText(/of 200 characters/)).not.toBeInTheDocument();

    await user.clear(field);
    await user.type(field, "y".repeat(165));
    expect(screen.getByText("165 of 200 characters")).toBeInTheDocument();
  });

  it("submits the trimmed title", async () => {
    const user = userEvent.setup();
    const { onCreate } = renderDialog();

    await user.type(screen.getByLabelText("Protocol title"), "  AURORA-301  ");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(onCreate).toHaveBeenCalledWith("AURORA-301");
  });

  it("keeps the typed title and shows the failure message after an error", async () => {
    const user = userEvent.setup();
    const { rerender } = renderDialog();

    await user.type(screen.getByLabelText("Protocol title"), "AURORA-301");
    rerender(
      <CreateProtocolDialog
        open
        organizationName="Northstar Clinical Research"
        organizationRole="owner"
        pending={false}
        error="Could not create the protocol workspace. Please try again."
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Protocol title")).toHaveValue("AURORA-301");
    expect(
      screen.getByText(
        "Could not create the protocol workspace. Please try again.",
      ),
    ).toBeInTheDocument();
  });

  it("disables the form while a creation is pending", () => {
    renderDialog({ pending: true });

    expect(screen.getByLabelText("Protocol title")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Creating workspace…" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });
});
