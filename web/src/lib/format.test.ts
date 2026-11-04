import { describe, expect, it } from "vitest";

import { formatSeconds } from "./format";

describe("formatSeconds", () => {
  it("formats timestamps and durations", () => {
    expect(formatSeconds(0)).toBe("0:00");
    expect(formatSeconds(3.023)).toBe("0:03");
    expect(formatSeconds(3.1)).toBe("0:03.1");
    expect(formatSeconds(9.0)).toBe("0:09");
    expect(formatSeconds(65.5)).toBe("1:05.5");
    expect(formatSeconds(59.96)).toBe("1:00"); // tenths carry into the next second
    expect(formatSeconds(600)).toBe("10:00");
    expect(formatSeconds(null)).toBe("—");
  });
});
