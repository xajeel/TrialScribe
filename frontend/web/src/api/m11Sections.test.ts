import { describe, expect, it } from "vitest";

import type { RequestOptions } from "./client";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { revisionViewFromApi } from "../product/governanceReviewFixtures";
import { restoreM11Section } from "./m11Sections";
import type { M11SectionRevision } from "./types";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000020";
const SECTION_NUMBER = "5";

describe("m11 sections api", () => {
  it("posts restore with expected revision and snapshot number", async () => {
    const calls: Array<{ path: string; options: RequestOptions | undefined }> = [];
    const fetcher: AuthorizedFetch = async <T>(
      path: string,
      options?: RequestOptions,
    ): Promise<T> => {
      calls.push({ path, options });
      return { id: "section-5" } as T;
    };

    await restoreM11Section(
      fetcher,
      ORGANIZATION_ID,
      CONVERSATION_ID,
      SECTION_NUMBER,
      4,
      1,
    );

    expect(calls[0]?.path).toBe(
      `/v1/ai/conversations/${CONVERSATION_ID}/m11-sections/${SECTION_NUMBER}/restore`,
    );
    expect(calls[0]?.options).toEqual({
      method: "POST",
      headers: { "X-Organization-ID": ORGANIZATION_ID },
      json: {
        expected_revision: 4,
        revision_number: 1,
      },
    });
  });

  it("maps generated and restored actions onto the revision view", () => {
    const record: M11SectionRevision = {
      id: "revision-3",
      section_id: "section-5",
      conversation_id: CONVERSATION_ID,
      organization_id: ORGANIZATION_ID,
      revision_number: 3,
      action: "generated",
      instructions: "",
      content: "Generated draft",
      status: "draft",
      author_account_id: null,
      created_at: "2026-08-15T00:00:00Z",
    };
    expect(revisionViewFromApi(record, 3, "account-1", {}).action).toBe(
      "generated",
    );
    expect(
      revisionViewFromApi({ ...record, action: "restored" }, 3, "account-1", {})
        .action,
    ).toBe("restored");
    expect(
      revisionViewFromApi({ ...record, action: "revised" }, 3, "account-1", {})
        .action,
    ).toBe("edited");
  });
});
