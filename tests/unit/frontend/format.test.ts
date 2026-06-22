import { describe, it, expect } from "vitest";
import { fmtPlat, fmtInt, prettySlug, wfmUrl } from "@/lib/format";

describe("format helpers", () => {
  it("formats platinum with a thousands separator and suffix", () => {
    expect(fmtPlat(1234)).toBe("1,234p");
  });

  it("returns an em dash for nullish platinum", () => {
    expect(fmtPlat(null)).toBe("—");
    expect(fmtPlat(undefined)).toBe("—");
  });

  it("formats integers with separators", () => {
    expect(fmtInt(32539253)).toBe("32,539,253");
  });

  it("title-cases underscore slugs", () => {
    expect(prettySlug("kronen_prime_handle")).toBe("Kronen Prime Handle");
  });

  it("builds a warframe.market url from a slug", () => {
    expect(wfmUrl("kronen_prime_set")).toBe(
      "https://warframe.market/items/kronen_prime_set",
    );
  });
});
