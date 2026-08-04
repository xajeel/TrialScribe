import { describe, expect, it } from "vitest";

import type { Conversation, M11Section } from "../api/types";
import {
  REVIEW_EXPORT_EMPTY,
  REVIEW_EXPORT_VIEW,
  REVIEW_USAGE_RUNNING,
  REVIEW_USAGE_VIEW,
  emptyUsageView,
  exportViewFromWorkspace,
  formatCostMicros,
} from "./deliveryAuditReviewFixtures";

const conversation: Conversation = {
  id: "conversation-1",
  organization_id: "org-1",
  owner_account_id: "account-1",
  title: "Test protocol",
  status: "active",
  collaborator_account_ids: [],
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-01T09:00:00Z",
  last_activity_at: "2026-08-01T09:00:00Z",
  archived_at: null,
};

function section(
  id: string,
  position: number,
  status: "draft" | "done",
  content: string,
): M11Section {
  return {
    id,
    conversation_id: conversation.id,
    organization_id: conversation.organization_id,
    catalog_version: "2025.1",
    section_number: String(position),
    title: `Section ${position}`,
    position,
    instructions: "",
    content,
    status,
    current_revision: position,
    completed_at: status === "done" ? "2026-08-01T10:00:00Z" : null,
    completed_by_account_id: status === "done" ? "account-1" : null,
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
  };
}

describe("delivery audit fixtures", () => {
  it("derives a fixed-order export manifest only from stored workspace facts", () => {
    const view = exportViewFromWorkspace(conversation, [
      section("section-2", 2, "draft", ""),
      section("section-1", 1, "done", "five stored words live here"),
    ]);

    expect(view.sections.map((item) => item.id)).toEqual([
      "section-1",
      "section-2",
    ]);
    expect(view.sections[0].words).toBe(5);
    expect(view.doneSections).toBe(1);
    expect(view.draftSections).toBe(1);
    expect(view.catalogVersion).toBe("2025.1");
    expect(view).not.toHaveProperty("citations");
    expect(view).not.toHaveProperty("requester");
  });

  it("does not claim one catalog when stored sections disagree", () => {
    const first = section("section-1", 1, "done", "Text");
    const second = { ...section("section-2", 2, "done", "Text"), catalog_version: "2026.1" };

    expect(exportViewFromWorkspace(conversation, [first, second]).catalogVersion).toBeNull();
  });

  it("keeps illustrative export and usage facts explicitly labeled", () => {
    expect(REVIEW_EXPORT_VIEW.fixtureNote).toMatch(/development review/i);
    expect(REVIEW_EXPORT_EMPTY.doneSections).toBe(0);
    expect(REVIEW_USAGE_VIEW.fixtureNote).toMatch(/illustrative/i);
    expect(REVIEW_USAGE_RUNNING.generations[0].outcome).toBe("running");
    expect(REVIEW_USAGE_RUNNING.generations[0].costMicros).toBeNull();
  });

  it("formats integer micros without losing exact sub-cent values", () => {
    expect(formatCostMicros(12_460_000)).toBe("$12.46");
    expect(formatCostMicros(42_100)).toBe("$0.0421");
    expect(formatCostMicros(0)).toBe("$0.00");
  });

  it("creates a factual empty usage view without provider records", () => {
    const view = emptyUsageView("conversation-1", "Test protocol");

    expect(view.summary.totalCostMicros).toBe(0);
    expect(view.summary.generationCount).toBe(0);
    expect(view.generations).toEqual([]);
  });
});
