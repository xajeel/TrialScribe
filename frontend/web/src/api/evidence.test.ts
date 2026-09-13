import { describe, expect, it } from "vitest";

import type { RequestOptions } from "./client";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { listEvidenceChunks } from "./evidence";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000020";
const FIRST_ID = "00000000-0000-4000-8000-000000000031";
const SECOND_ID = "00000000-0000-4000-8000-000000000032";

describe("evidence api", () => {
  it("repeats ids as query parameters", async () => {
    const calls: Array<{ path: string; options: RequestOptions | undefined }> = [];
    const fetcher: AuthorizedFetch = async <T>(
      path: string,
      options?: RequestOptions,
    ): Promise<T> => {
      calls.push({ path, options });
      return { items: [] } as T;
    };

    await listEvidenceChunks(fetcher, ORGANIZATION_ID, CONVERSATION_ID, [
      FIRST_ID,
      SECOND_ID,
    ]);

    expect(calls[0]?.path).toBe(
      `/v1/ai/conversations/${CONVERSATION_ID}/evidence-chunks?ids=${FIRST_ID}&ids=${SECOND_ID}`,
    );
    expect(calls[0]?.options?.headers).toEqual({
      "X-Organization-ID": ORGANIZATION_ID,
    });
  });
});
