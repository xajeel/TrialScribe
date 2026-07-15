import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the platform-ready shell", () => {
    const markup = renderToStaticMarkup(<App />);

    expect(markup).toContain("<h1");
    expect(markup).toContain("TrialScribe");
    expect(markup).toContain("The platform shell is ready.");
  });
});
