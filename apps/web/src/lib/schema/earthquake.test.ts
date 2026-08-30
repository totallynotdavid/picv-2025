import { describe, expect, it } from "vitest";

import { earthquakeSchema, toEarthquakeInput } from "./earthquake";

describe("earthquake input", () => {
  it("converts the form timestamp to UTC day and HHMM fields", () => {
    const input = toEarthquakeInput({
      magnitude: 8.0,
      depth: 12,
      latitude: -20.5,
      longitude: -70.5,
      datetime: "2026-08-30T23:45:00-05:00",
    });

    expect(input).toEqual({
      Mw: 8.0,
      h: 12,
      lat0: -20.5,
      lon0: -70.5,
      dia: "31",
      hhmm: "0445",
    });
  });

  it("rejects values outside the form's physical input limits", () => {
    const result = earthquakeSchema.safeParse({
      magnitude: 6.4,
      depth: -1,
      latitude: -91,
      longitude: 181,
      datetime: "",
    });

    expect(result.success).toBe(false);
  });
});
