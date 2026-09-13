import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { renderApp } from "../test/renderApp";

function mockAnonymousBootstrap(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (): Promise<Response> => {
      return new Response(
        JSON.stringify({ detail: "Invalid authentication credentials" }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        },
      );
    }),
  );
}

describe("AuthPage", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
    mockAnonymousBootstrap();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the complete Sign in experience", async () => {
    renderApp({ route: "/login" });

    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveClass("brand-logo");
    expect(screen.queryByText("Sign in to TrialScribe")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Create an account" }),
    ).toHaveAttribute("href", "/signup");
    expect(
      screen.getByText("Every claim connected to its evidence."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/intelligent evidence archive/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "From account to first protocol.",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "What happens next" }),
    ).not.toBeInTheDocument();
  });

  it("shows and hides the password without changing its value", async () => {
    const user = userEvent.setup();
    renderApp({ route: "/login" });

    const password = await screen.findByLabelText("Password");
    await user.type(password, "correct-horse-battery");

    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("correct-horse-battery");

    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("correct-horse-battery");
  });

  it("renders the complete Create Account experience", async () => {
    renderApp({ route: "/signup" });

    expect(
      await screen.findByRole("heading", {
        name: "Get started",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveClass("brand-logo");
    expect(
      screen.queryByText("Create your TrialScribe account"),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute(
      "autocomplete",
      "email",
    );
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(screen.getAllByRole("link", { name: "Sign in" })).toHaveLength(2);
    expect(
      screen.getByRole("heading", {
        name: "From account to first protocol.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "What happens next" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Establish your researcher identity.")).toBeInTheDocument();
    expect(
      screen.getByText("Verify academic affiliation via email."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Start drafting your first clinical study."),
    ).toBeInTheDocument();
  });

  it("shows and hides the Create Account password without changing its value", async () => {
    const user = userEvent.setup();
    renderApp({ route: "/signup" });

    const password = await screen.findByLabelText("Password");
    await user.type(password, "correct-horse-battery");

    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("correct-horse-battery");

    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("correct-horse-battery");
  });

  it("reports empty, short, and valid Create Account passwords", async () => {
    const user = userEvent.setup();
    renderApp({ route: "/signup" });

    const password = await screen.findByLabelText("Password");
    const feedback = document.getElementById("signup-password-feedback");

    expect(feedback).toHaveTextContent("Use at least 15 characters");

    await user.type(password, "short");
    expect(feedback).toHaveTextContent("15+ characters required");

    await user.type(password, "-password-long");
    expect(feedback).toHaveTextContent("Password strength validated");
    expect(password).toHaveValue("short-password-long");
  });
});
