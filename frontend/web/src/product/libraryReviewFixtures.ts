import type { Conversation } from "../api/types";
import type { ProtocolDetail } from "../workspace/useProtocolLibrary";

/** Sample protocols used only by the development review route, never by the app. */

const ORGANIZATION_ID = "00000000-0000-4000-8000-0000000000aa";
const OWNER_ID = "00000000-0000-4000-8000-0000000000bb";

function fixture(
  id: string,
  title: string,
  lastActivity: string,
): Conversation {
  return {
    id,
    organization_id: ORGANIZATION_ID,
    owner_account_id: OWNER_ID,
    title,
    status: "active",
    collaborator_account_ids: [],
    created_at: "2026-07-01T09:00:00Z",
    updated_at: lastActivity,
    last_activity_at: lastActivity,
    archived_at: null,
  };
}

export const REVIEW_PROTOCOLS: Conversation[] = [
  fixture(
    "review-aurora",
    "AURORA-301 — Phase III oncology protocol with a deliberately long study title",
    "2026-07-31T14:32:00Z",
  ),
  fixture("review-lumen", "LUMEN-204 dose escalation", "2026-07-30T17:05:00Z"),
  fixture("review-orbit", "ORBIT registry amendment", "2026-07-21T10:18:00Z"),
  fixture("review-pathway", "PATHWAY-404", "2026-07-18T08:40:00Z"),
];

export const REVIEW_DETAILS: Record<string, ProtocolDetail> = {
  "review-aurora": {
    sections: { done: 8, total: 14 },
    sources: 6,
    processing: 0,
    failed: 1,
  },
  "review-lumen": {
    sections: { done: 12, total: 14 },
    sources: 9,
    processing: 1,
    failed: 0,
  },
  "review-orbit": {
    sections: { done: 14, total: 14 },
    sources: 4,
    processing: 0,
    failed: 0,
  },
  "review-pathway": {
    sections: { done: 0, total: 14 },
    sources: 0,
    processing: 0,
    failed: 0,
  },
};

export const REVIEW_ORGANIZATION = {
  id: ORGANIZATION_ID,
  name: "Northstar Clinical Research",
  role: "owner",
  created_at: "2026-07-01T09:00:00Z",
} as const;
