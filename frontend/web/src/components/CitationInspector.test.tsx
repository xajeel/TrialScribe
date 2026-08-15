import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EvidenceChunkRecord } from "../api/types";
import { CitationInspector } from "./CitationInspector";

const CHUNK: EvidenceChunkRecord = {
  id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  conversation_id: "conversation-1",
  organization_id: "organization-1",
  source_kind: "trial_data",
  source_identity: "trial-1",
  page_number: 2,
  start_char: 0,
  end_char: 12,
  text: "Age 18 years",
};

describe("CitationInspector", () => {
  it("shows source type, identity, page, and passage", () => {
    render(
      <CitationInspector chunk={CHUNK} missing={false} onClose={vi.fn()} />,
    );

    expect(screen.getByRole("heading", { name: "Citation" })).toBeInTheDocument();
    expect(screen.getByText("Trial data")).toBeInTheDocument();
    expect(screen.getByText("trial-1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Age 18 years")).toBeInTheDocument();
  });

  it("shows the missing copy when the chunk is unknown", () => {
    render(<CitationInspector chunk={null} missing onClose={vi.fn()} />);
    expect(
      screen.getByText("That source is not in this conversation."),
    ).toBeInTheDocument();
  });
});
