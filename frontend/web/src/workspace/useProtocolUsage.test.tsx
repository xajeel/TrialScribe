import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type { UsageRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { formatCostMicros } from "../product/deliveryAuditReviewFixtures";
import {
  USAGE_LOAD_ERROR,
  useProtocolUsage,
  type ProtocolUsageController,
} from "./useProtocolUsage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";

function usageRecord(): UsageRecord {
  return {
    protocol_title: "AURORA-301",
    protocol_id: CONVERSATION_ID,
    summary: {
      total_cost_micros: 4,
      input_tokens: 20,
      output_tokens: 10,
      successful_jobs: 1,
      failed_or_cancelled: 0,
      generation_count: 1,
      pricing_basis: "Versioned provider pricing",
      updated_at: "2026-08-13T12:00:00Z",
    },
    generations: [],
  };
}

function createFetcher(
  handler: (
    path: string,
    options: RequestOptions | undefined,
  ) => unknown | Promise<unknown>,
): { fetcher: AuthorizedFetch; calls: Array<{ path: string; options: RequestOptions | undefined }> } {
  const calls: Array<{ path: string; options: RequestOptions | undefined }> = [];
  async function fetcher<T>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    calls.push({ path, options });
    return (await handler(path, options)) as T;
  }
  return { fetcher, calls };
}

function Harness({
  fetcher,
  enabled,
  onController,
}: {
  fetcher: AuthorizedFetch;
  enabled: boolean;
  onController: (controller: ProtocolUsageController) => void;
}) {
  const controller = useProtocolUsage({
    organizationId: ORGANIZATION_ID,
    conversationId: CONVERSATION_ID,
    fetcher,
    enabled,
  });
  onController(controller);
  return (
    <div>
      <p data-testid="loading">{controller.loading ? "yes" : "no"}</p>
      <p data-testid="error">{controller.error ? "yes" : "no"}</p>
      <p data-testid="total">
        {controller.view === null
          ? ""
          : formatCostMicros(controller.view.summary.totalCostMicros)}
      </p>
    </div>
  );
}

describe("useProtocolUsage", () => {
  it("does not fetch when disabled", async () => {
    const { fetcher, calls } = createFetcher(() => {
      throw new Error("must not fetch");
    });

    render(
      <Harness
        fetcher={fetcher}
        enabled={false}
        onController={() => undefined}
      />,
    );

    expect(calls).toEqual([]);
    expect(screen.getByTestId("loading")).toHaveTextContent("no");
  });

  it("loads stored usage totals without posting a job", async () => {
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.includes("/v1/jobs/usage") && options?.method === undefined) {
        return usageRecord();
      }
      throw new Error(`Unexpected request: ${options?.method ?? "GET"} ${path}`);
    });

    render(
      <Harness
        fetcher={fetcher}
        enabled={true}
        onController={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("total")).toHaveTextContent(formatCostMicros(4));
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.path).toContain(`conversation_id=${CONVERSATION_ID}`);
    expect(calls.some((call) => call.options?.method === "POST")).toBe(false);
    expect(calls.some((call) => call.options?.method === "PATCH")).toBe(false);
  });

  it("exposes a public load error", async () => {
    const { fetcher } = createFetcher(() => {
      throw new Error("upstream failed");
    });

    render(
      <Harness
        fetcher={fetcher}
        enabled={true}
        onController={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("error")).toHaveTextContent("yes");
    });
    expect(USAGE_LOAD_ERROR).toMatch(/could not load usage/i);
  });
});
