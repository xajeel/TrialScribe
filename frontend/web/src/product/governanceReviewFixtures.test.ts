import { describe, expect, it } from "vitest";

import type {
  Conversation,
  DocumentRecord,
  M11Section,
  M11SectionRevision,
} from "../api/types";
import {
  READINESS_REVIEW_INCOMPLETE,
  READINESS_REVIEW_READY,
  REVISION_REVIEW_COMPARISON,
  readinessForReview,
  readinessFromWorkspace,
  revisionRowsForReview,
  revisionViewFromApi,
  type GovernanceReviewState,
} from "./governanceReviewFixtures";

const conversation: Conversation = {
  id: "conversation-1",
  organization_id: "org-1",
  owner_account_id: "account-1",
  title: "AURORA-301",
  status: "active",
  collaborator_account_ids: [],
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-03T00:00:00Z",
  last_activity_at: "2026-07-03T00:00:00Z",
  archived_at: null,
};

function section(number: string, position: number, status: "draft" | "done"): M11Section {
  return {
    id: `section-${number}`,
    conversation_id: conversation.id,
    organization_id: conversation.organization_id,
    catalog_version: "2025.1",
    section_number: number,
    title: `Section ${number}`,
    position,
    instructions: "",
    content: status === "done" ? "Stored section text" : "",
    status,
    current_revision: status === "done" ? 2 : 0,
    completed_at: status === "done" ? "2026-07-02T00:00:00Z" : null,
    completed_by_account_id: status === "done" ? "account-1" : null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: `2026-07-0${position}T00:00:00Z`,
  };
}

function document(status: "pending" | "ready" | "failed"): DocumentRecord {
  return {
    id: `document-${status}`,
    conversation_id: conversation.id,
    organization_id: conversation.organization_id,
    uploaded_by_account_id: "account-1",
    kind: "research_document",
    filename: `${status}.pdf`,
    content_type: "application/pdf",
    byte_size: 100,
    status,
    error: status === "failed" ? "private detail" : null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-04T00:00:00Z",
  };
}

describe("governance review models", () => {
  it("maps API revisions without inventing a person's name", () => {
    const record: M11SectionRevision = {
      id: "revision-2",
      section_id: "section-5",
      conversation_id: conversation.id,
      organization_id: conversation.organization_id,
      revision_number: 2,
      action: "done",
      instructions: "",
      content: "Stored text",
      status: "done",
      author_account_id: "account-2",
      created_at: "2026-07-03T00:00:00Z",
    };
    const mapped = revisionViewFromApi(record, 2, "account-1");
    expect(mapped.actionLabel).toBe("Marked done");
    expect(mapped.authorLabel).toBe("Collaborator");
    expect(mapped.current).toBe(true);
  });

  it("keeps sections in catalog order and omits unknown citation facts", () => {
    const mapped = readinessFromWorkspace(
      conversation,
      [section("2", 2, "done"), section("1", 1, "draft")],
      [document("ready")],
    );
    expect(mapped.sections.map((item) => item.sectionNumber)).toEqual(["1", "2"]);
    expect(mapped.summary.citations).toBeUndefined();
    expect(mapped.sections[0].citations).toBeUndefined();
  });

  it("derives fixed source and empty-section issues without raw errors", () => {
    const mapped = readinessFromWorkspace(
      conversation,
      [section("1", 1, "draft")],
      [document("pending"), document("failed")],
    );
    expect(mapped.issues.map((issue) => issue.title)).toEqual([
      "Source processing is not complete",
      "Source could not be prepared",
      "Section has no content",
    ]);
    expect(JSON.stringify(mapped)).not.toContain("private detail");
  });

  it("marks readiness only when every known section and source is ready", () => {
    const ready = readinessFromWorkspace(
      conversation,
      [section("1", 1, "done")],
      [document("ready")],
    );
    const incomplete = readinessFromWorkspace(
      conversation,
      [section("1", 1, "draft")],
      [document("ready")],
    );
    expect(ready.ready).toBe(true);
    expect(incomplete.ready).toBe(false);
  });

  it("provides every requested deterministic review state", () => {
    const states: GovernanceReviewState[] = [
      "revisions-timeline",
      "revisions-preview",
      "revisions-empty",
      "revisions-compare",
      "revisions-restore",
      "revisions-restored",
      "readiness-incomplete",
      "readiness-attention",
      "readiness-filtered",
      "readiness-ready",
      "readiness-retry",
    ];
    expect(states).toHaveLength(11);
    expect(revisionRowsForReview("revisions-empty")).toEqual([]);
    expect(revisionRowsForReview("revisions-preview").length).toBeGreaterThan(0);
    expect(REVISION_REVIEW_COMPARISON.earlierSegments).toBeDefined();
    expect(READINESS_REVIEW_INCOMPLETE.fixtureNote).toMatch(/development review/i);
    expect(READINESS_REVIEW_READY.ready).toBe(true);
    expect(
      readinessForReview("readiness-retry").issues.some(
        (issue) => issue.state === "retrying",
      ),
    ).toBe(true);
  });
});
