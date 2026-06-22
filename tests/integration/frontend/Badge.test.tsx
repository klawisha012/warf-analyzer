import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import Badge from "@/components/Badge";

describe("<Badge>", () => {
  it("renders its children", () => {
    const { getByText } = render(() => <Badge variant="good">Online</Badge>);
    expect(getByText("Online")).toBeInTheDocument();
  });

  it("maps the variant onto a chip class", () => {
    const { getByText } = render(() => <Badge variant="good">Online</Badge>);
    expect(getByText("Online").className).toContain("online");
  });

  it("defaults to the neutral chip", () => {
    const { getByText } = render(() => <Badge>Plain</Badge>);
    expect(getByText("Plain").className).toBe("chip");
  });
});
