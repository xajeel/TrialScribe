import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "./api/client";
import { renderApp } from "./test/renderApp";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the landing page to anonymous visitors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, { detail: "Invalid authentication credentials" }),
      ),
    );

    renderApp();

    expect(
      await screen.findByRole("heading", {
        name: /draft a protocol your reviewers can trace/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveClass("brand-logo");

    expect(
      screen.getByRole("heading", {
        name: /a disciplined workflow for regulated writing/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: /a citation matters only when a reviewer can verify it/i,
      }),
    ).toBeInTheDocument();

    for (const link of screen.getAllByRole("link", {
      name: "Start a protocol",
    })) {
      expect(link).toHaveAttribute("href", "/signup");
    }
    for (const link of screen.getAllByRole("link", { name: "Sign in" })) {
      expect(link).toHaveAttribute("href", "/login");
    }
  });

  it("opens the workspace from the landing page for an active session", async () => {
    const account = {
      id: "account-1",
      email: "researcher@example.com",
      is_active: true,
      created_at: "2026-07-29T10:00:00Z",
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/v1/auth/refresh")) {
          return jsonResponse(200, {
            access_token: "access-token",
            token_type: "bearer",
            expires_in: 300,
          });
        }
        if (url.endsWith("/v1/auth/me")) {
          return jsonResponse(200, account);
        }
        return jsonResponse(404, { detail: "Not found" });
      }),
    );

    renderApp();

    expect(
      await screen.findByRole("heading", {
        name: /draft a protocol your reviewers can trace/i,
      }),
    ).toBeInTheDocument();
    for (const link of await screen.findAllByRole("link", {
      name: "Open workspace",
    })) {
      expect(link).toHaveAttribute("href", "/protocols");
    }
  });
  it("redirects the legacy workspace route to the protocol library", async () => {
    const account = {
      id: "account-1",
      email: "researcher@example.com",
      is_active: true,
      created_at: "2026-07-29T10:00:00Z",
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/v1/auth/refresh")) {
          return jsonResponse(200, {
            access_token: "access-token",
            token_type: "bearer",
            expires_in: 300,
          });
        }
        if (url.endsWith("/v1/auth/me")) {
          return jsonResponse(200, account);
        }
        if (url.includes("/v1/organizations")) {
          return jsonResponse(200, [
            {
              id: "org-1",
              name: "Acme Trials",
              role: "owner",
              created_at: "2026-07-29T10:00:00Z",
            },
          ]);
        }
        if (url.includes("/v1/ai/conversations")) {
          return jsonResponse(200, { items: [], next_cursor: null });
        }
        return jsonResponse(404, { detail: "Not found" });
      }),
    );

    renderApp({ route: "/workspace" });

    expect(
      await screen.findByRole("heading", { name: "Protocol workspaces" }),
    ).toBeInTheDocument();
  });

  it("renders the workspace review, export, and usage routes for a signed-in account", async () => {
    const account = {
      id: "account-1",
      email: "researcher@example.com",
      is_active: true,
      created_at: "2026-07-29T10:00:00Z",
    };
    const conversation = {
      id: "conversation-1",
      organization_id: "org-1",
      owner_account_id: account.id,
      title: "AURORA-301",
      status: "active",
      collaborator_account_ids: [],
      created_at: "2026-07-29T10:00:00Z",
      updated_at: "2026-07-29T10:00:00Z",
      last_activity_at: "2026-07-29T10:00:00Z",
      archived_at: null,
    };

    const stub = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/v1/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "access-token",
          token_type: "bearer",
          expires_in: 300,
        });
      }
      if (url.endsWith("/v1/auth/me")) {
        return jsonResponse(200, account);
      }
      if (url.includes("/v1/organizations")) {
        return jsonResponse(200, [
          {
            id: "org-1",
            name: "Acme Trials",
            role: "owner",
            created_at: "2026-07-29T10:00:00Z",
          },
        ]);
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      if (url.includes("/documents")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      if (url.includes("/m11-sections")) {
        return jsonResponse(200, { catalog_version: "2025.1", items: [] });
      }
      if (url.includes("/v1/jobs/readiness")) {
        return jsonResponse(200, {
          checked: false,
          ready: false,
          stale: false,
          job_id: null,
          computed_at: null,
          protocol_title: conversation.title,
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
        });
      }
      if (url.includes("/v1/ai/conversations/conversation-1")) {
        return jsonResponse(200, conversation);
      }
      if (url.includes("/v1/jobs/usage")) {
        return jsonResponse(200, {
          protocol_title: conversation.title,
          protocol_id: conversation.id,
          summary: {
            total_cost_micros: 0,
            input_tokens: 0,
            output_tokens: 0,
            successful_jobs: 0,
            failed_or_cancelled: 0,
            generation_count: 0,
            pricing_basis: "Versioned provider pricing",
            updated_at: null,
          },
          generations: [],
        });
      }
      return jsonResponse(404, { detail: "Not found" });
    });

    vi.stubGlobal("fetch", stub);
    const instructions = renderApp({
      route: "/workspace/conversation-1/instructions",
    });
    expect(
      await screen.findByRole("heading", { name: "Writing instructions" }),
    ).toBeInTheDocument();
    instructions.unmount();

    tokenStore.clear();
    vi.stubGlobal("fetch", stub);
    const progress = renderApp({ route: "/workspace/conversation-1/progress" });
    expect(
      await screen.findByRole("heading", { name: "Protocol progress" }),
    ).toBeInTheDocument();
    progress.unmount();

    tokenStore.clear();
    vi.stubGlobal("fetch", stub);
    const revisions = renderApp({
      route: "/workspace/conversation-1/revisions",
    });
    expect(
      await screen.findByRole("heading", { name: "Revision history" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /restore as new revision/i }),
    ).not.toBeInTheDocument();
    revisions.unmount();

    tokenStore.clear();
    vi.stubGlobal("fetch", stub);
    const readiness = renderApp({ route: "/workspace/conversation-1/readiness" });
    expect(
      await screen.findByRole("heading", { name: "Protocol readiness" }),
    ).toBeInTheDocument();
    readiness.unmount();

    tokenStore.clear();
    vi.stubGlobal("fetch", stub);
    const exportPage = renderApp({
      route: "/workspace/conversation-1/export",
    });
    expect(
      await screen.findByRole("heading", { name: "Export protocol" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/complete at least one section before exporting/i),
    ).toBeInTheDocument();
    exportPage.unmount();

    tokenStore.clear();
    vi.stubGlobal("fetch", stub);
    renderApp({ route: "/workspace/conversation-1/usage" });
    expect(
      await screen.findByRole("heading", { name: "Usage and cost" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/provider usage records are not connected/i),
    ).not.toBeInTheDocument();
  });

  it("restores a live snapshot onto the current draft", async () => {
    const user = userEvent.setup();
    const account = {
      id: "account-1",
      email: "researcher@example.com",
      is_active: true,
      created_at: "2026-07-29T10:00:00Z",
    };
    const conversation = {
      id: "conversation-1",
      organization_id: "org-1",
      owner_account_id: account.id,
      title: "AURORA-301",
      status: "active",
      collaborator_account_ids: [],
      created_at: "2026-07-29T10:00:00Z",
      updated_at: "2026-07-29T10:00:00Z",
      last_activity_at: "2026-07-29T10:00:00Z",
      archived_at: null,
    };
    const section = {
      id: "section-5",
      conversation_id: conversation.id,
      organization_id: conversation.organization_id,
      catalog_version: "2025.1",
      section_number: "5",
      title: "Trial Population",
      position: 5,
      instructions: "",
      content: "Current draft",
      status: "draft",
      current_revision: 2,
      completed_at: null,
      completed_by_account_id: null,
      created_at: "2026-07-29T10:00:00Z",
      updated_at: "2026-07-29T10:00:00Z",
    };
    const revisions = [
      {
        id: "revision-2",
        section_id: section.id,
        conversation_id: conversation.id,
        organization_id: conversation.organization_id,
        revision_number: 2,
        action: "revised",
        instructions: "",
        content: "Current draft",
        status: "draft",
        author_account_id: null,
        created_at: "2026-07-30T10:00:00Z",
      },
      {
        id: "revision-1",
        section_id: section.id,
        conversation_id: conversation.id,
        organization_id: conversation.organization_id,
        revision_number: 1,
        action: "generated",
        instructions: "",
        content: "First draft",
        status: "draft",
        author_account_id: null,
        created_at: "2026-07-29T10:00:00Z",
      },
    ];

    const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/v1/auth/refresh")) {
        return jsonResponse(200, {
          access_token: "access-token",
          token_type: "bearer",
          expires_in: 300,
        });
      }
      if (url.endsWith("/v1/auth/me")) {
        return jsonResponse(200, account);
      }
      if (url.includes("/v1/organizations")) {
        return jsonResponse(200, [
          {
            id: "org-1",
            name: "Acme Trials",
            role: "owner",
            created_at: "2026-07-29T10:00:00Z",
          },
        ]);
      }
      if (url.includes("/messages")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      if (url.includes("/documents")) {
        return jsonResponse(200, { items: [], next_cursor: null });
      }
      if (url.includes("/restore")) {
        return jsonResponse(200, {
          ...section,
          content: "First draft",
          current_revision: 3,
          updated_at: "2026-07-31T10:00:00Z",
        });
      }
      if (url.includes("/revisions")) {
        return jsonResponse(200, { items: revisions, next_after_revision: null });
      }
      if (url.includes("/m11-sections")) {
        return jsonResponse(200, {
          catalog_version: "2025.1",
          items: [section],
        });
      }
      if (url.includes("/v1/ai/conversations/conversation-1")) {
        return jsonResponse(200, conversation);
      }
      return jsonResponse(404, { detail: "Not found" });
    });

    vi.stubGlobal("fetch", stub);
    renderApp({ route: "/workspace/conversation-1/revisions" });

    expect(
      await screen.findByRole("heading", { name: "Revision history" }),
    ).toBeInTheDocument();
    const revisionOne = await screen.findByRole("button", { name: /revision 1/i });
    const row = revisionOne.closest("li");
    expect(row).not.toBeNull();
    await user.click(revisionOne);
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Preview" }));
    expect(
      screen.getByRole("button", { name: /restore as new revision/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /restore as new revision/i }));
    await user.click(
      await screen.findByRole("button", { name: "Restore as revision 3" }),
    );

    await waitFor(() => {
      const restoreCall = stub.mock.calls.find(([input, init]) => {
        return String(input).includes("/restore") && init?.method === "POST";
      });
      expect(restoreCall).toBeDefined();
      expect(JSON.parse(String(restoreCall?.[1]?.body))).toEqual({
        expected_revision: 2,
        revision_number: 1,
      });
    });
  });

  it("renders the evidence and rewrite review routes without a session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, { detail: "Invalid authentication credentials" }),
      ),
    );

    const evidence = renderApp({ route: "/review/evidence/pdf" });
    expect(
      await screen.findByRole("heading", { name: "Evidence inspector" }),
    ).toBeInTheDocument();
    evidence.unmount();

    const rewrite = renderApp({ route: "/review/rewrite/alternatives" });
    expect(
      await screen.findByRole("heading", { name: "Rewrite alternatives" }),
    ).toBeInTheDocument();
    rewrite.unmount();

    renderApp({ route: "/review/compare" });
    expect(
      await screen.findByRole("heading", { name: "Compare wording" }),
    ).toBeInTheDocument();
  });

  it("renders the Export and Usage review routes without a session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, { detail: "Invalid authentication credentials" }),
      ),
    );

    const exportReview = renderApp({ route: "/review/export/building" });
    expect(
      await screen.findByRole("heading", { name: "Export protocol" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Preparing export" }),
    ).toBeInTheDocument();
    exportReview.unmount();

    renderApp({ route: "/review/usage/expanded" });
    expect(
      await screen.findByRole("heading", { name: "Usage and cost" }),
    ).toBeInTheDocument();
    expect(screen.getByText("JOB-7729-X")).toBeInTheDocument();
  });

  it("renders the Profile and Members review routes without a session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, { detail: "Invalid authentication credentials" }),
      ),
    );

    const profile = renderApp({ route: "/review/profile" });
    expect(
      await screen.findByRole("heading", { name: "Profile and settings" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/development review/i);
    profile.unmount();

    renderApp({ route: "/review/members/success" });
    expect(
      await screen.findByRole("heading", {
        name: "Northstar Clinical Research",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Invitation created")).toBeInTheDocument();
  });

  it("renders protected organization access and links it from the account menu", async () => {
    const account = {
      id: "account-1",
      email: "researcher@example.com",
      is_active: true,
      created_at: "2026-07-29T10:00:00Z",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/v1/auth/refresh")) {
          return jsonResponse(200, {
            access_token: "access-token",
            token_type: "bearer",
            expires_in: 300,
          });
        }
        if (url.endsWith("/v1/auth/me")) {
          return jsonResponse(200, account);
        }
        if (url.endsWith("/v1/organizations/org-1/members")) {
          return jsonResponse(200, [
            {
              id: "membership-1",
              organization_id: "org-1",
              account_id: account.id,
              role: "owner",
              created_at: "2026-07-29T10:00:00Z",
              identity: {
                account_id: account.id,
                email: account.email,
                is_active: true,
              },
            },
          ]);
        }
        if (url.endsWith("/v1/organizations/org-1/invitations")) {
          return jsonResponse(200, []);
        }
        if (url.endsWith("/v1/organizations")) {
          return jsonResponse(200, [
            {
              id: "org-1",
              name: "Acme Trials",
              role: "owner",
              created_at: "2026-07-29T10:00:00Z",
            },
          ]);
        }
        return jsonResponse(404, { detail: "Not found" });
      }),
    );
    const user = userEvent.setup();

    renderApp({ route: "/organization/members" });
    expect(
      await screen.findByRole("heading", { name: "Acme Trials" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("1 member")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Account menu" }));
    expect(
      screen.getByRole("link", { name: "Organization access" }),
    ).toHaveAttribute("href", "/organization/members");
  });
});
