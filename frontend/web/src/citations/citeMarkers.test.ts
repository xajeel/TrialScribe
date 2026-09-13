import { describe, expect, it } from "vitest";

import { sourceKindLabel, splitCitedText } from "./citeMarkers";

const CHUNK_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

describe("citeMarkers", () => {
  it("splits canonical cite markers from surrounding text", () => {
    expect(
      splitCitedText(`Aged 18 years [cite:${CHUNK_ID}] at screening.`),
    ).toEqual([
      { type: "text", value: "Aged 18 years " },
      { type: "cite", id: CHUNK_ID },
      { type: "text", value: " at screening." },
    ]);
  });

  it("leaves unresolved or malformed markers as text", () => {
    expect(splitCitedText("See [cite:not-a-uuid] and [cite].")).toEqual([
      { type: "text", value: "See [cite:not-a-uuid] and [cite]." },
    ]);
  });

  it("labels stored source kinds for the inspector", () => {
    expect(sourceKindLabel("trial_data")).toBe("Trial data");
    expect(sourceKindLabel("research_document")).toBe("Uploaded document");
    expect(sourceKindLabel("web")).toBe("Internet source");
    expect(sourceKindLabel("other")).toBe("Other source");
  });
});
