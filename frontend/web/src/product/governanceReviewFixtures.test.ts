import { describe, expect, it } from "vitest";

import type {
  Conversation,
  DocumentRecord,
  M11Section,
  M11SectionRevision,
  ReadinessRecord,
} from "../api/types";
import {
  READINESS_REVIEW_INCOMPLETE,
  READINESS_REVIEW_READY,
  REVISION_REVIEW_COMPARISON,
  readinessForReview,
  readinessFromWorkspace,
  readinessViewFromApi,
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
    const mapped = revisionViewFromApi(record, 2, "account-1", {
      "account-2": {
        account_id: "account-2",
        email: "collaborator@example.com",
        is_active: true,
      },
    });
    expect(mapped.actionLabel).toBe("Marked done");
    expect(mapped.authorLabel).toBe("collaborator@example.com");
    expect(mapped.current).toBe(true);
    expect(revisionViewFromApi(record, 2, "account-1", {}).authorLabel).toBe(
      "Unavailable account",
    );
    expect(
      revisionViewFromApi(
        { ...record, author_account_id: "account-1" },
        2,
        "account-1",
        {},
      ).authorLabel,
    ).toBe("You");
    expect(
      revisionViewFromApi(
        { ...record, author_account_id: null },
        2,
        "account-1",
        {},
      ).authorLabel,
    ).toBe("System");
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

  it("maps a stored snapshot including retry-check", () => {
    const unchecked: ReadinessRecord = {
      checked: false,
      ready: false,
      stale: false,
      job_id: null,
      computed_at: null,
      protocol_title: "AURORA-301",
      protocol_id: conversation.id,
      summary: {
        total_sections: 0,
        done_sections: 0,
        draft_sections: 0,
        ready_sources: 0,
        pending_sources: 0,
        failed_sources: 0,
        latest_activity: null,
        citations: null,
      },
      issues: [],
      sections: [],
    };
    const empty = readinessViewFromApi(unchecked);
    expect(empty.ready).toBe(false);
    expect(empty.issues).toEqual([]);
    expect(empty.sections).toEqual([]);
    expect(empty.summary.doneSections).toBe(0);

    const mapped = readinessViewFromApi({
      ...unchecked,
      checked: true,
      ready: false,
      issues: [
        {
          id: "stale-check",
          title: "Protocol changed since last check",
          detail: "Run the check again.",
          severity: "warning",
          code: "stale_check",
          action: "retry-check",
          action_label: "Check again",
          section_number: null,
        },
      ],
      summary: {
        total_sections: 14,
        done_sections: 13,
        draft_sections: 1,
        ready_sources: 1,
        pending_sources: 0,
        failed_sources: 0,
        latest_activity: "2026-08-15T12:00:00Z",
        citations: { resolved: 1, needing_review: 0 },
      },
    });
    expect(mapped.ready).toBe(false);
    expect(mapped.issues[0]?.id).toBe("stale-check");
    expect(mapped.issues[0]?.action).toBe("retry-check");
    expect(mapped.summary.doneSections).toBe(13);
  });
});
