import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CitedSectionText } from "./CitedSectionText";

const CHUNK_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

describe("CitedSectionText", () => {
  it("turns a marker into a button whose accessible name includes the id", () => {
    const onInspect = vi.fn();
    render(
      <CitedSectionText
        content={`Aged 18 years [cite:${CHUNK_ID}].`}
        onInspect={onInspect}
      />,
    );

    const button = screen.getByRole("button", {
      name: `Inspect citation ${CHUNK_ID}`,
    });
    expect(button).toHaveTextContent("[cite]");
    button.click();
    expect(onInspect).toHaveBeenCalledWith(CHUNK_ID);
  });
});
