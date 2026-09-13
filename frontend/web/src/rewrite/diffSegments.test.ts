import { describe, expect, it } from "vitest";

import { diffSegments } from "./diffSegments";

describe("diffSegments", () => {
  it("returns one unchanged segment when the strings match", () => {
    expect(diffSegments("Primary endpoint is FVC.", "Primary endpoint is FVC.")).toEqual([
      { kind: "unchanged", text: "Primary endpoint is FVC." },
    ]);
  });

  it("marks replaced words as removed then added", () => {
    expect(diffSegments("The cat sat", "The dog sat")).toEqual([
      { kind: "unchanged", text: "The" },
      { kind: "removed", text: "cat" },
      { kind: "added", text: "dog" },
      { kind: "unchanged", text: "sat" },
    ]);
  });
});
