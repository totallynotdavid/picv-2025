import { isHttpError } from "@sveltejs/kit";
import { describe, expect, it } from "vitest";

import { assertOutputAccessible } from "./outputs";
import type { SimulationDetails } from "./simulation-details";

const SIM: SimulationDetails = {
  id: "sim-1",
  userId: "user-1",
  params: null,
  createdAt: new Date(),
  submissionError: null,
  status: "completed",
  details: null,
  step: null,
  stepIndex: null,
  totalSteps: null,
  calculation: null,
  travelTimes: null,
  error: null,
  outputs: ["max_height_map"],
  startedAt: null,
  finishedAt: null,
};

describe("assertOutputAccessible", () => {
  it("allows a name present in the simulation outputs", () => {
    expect(() => assertOutputAccessible(SIM, "max_height_map")).not.toThrow();
  });

  it("rejects with 404 when the simulation does not exist", () => {
    try {
      assertOutputAccessible(undefined, "max_height_map");
      throw new Error("expected assertOutputAccessible to throw");
    } catch (err) {
      expect(isHttpError(err)).toBe(true);
      if (isHttpError(err)) expect(err.status).toBe(404);
    }
  });

  it("rejects with 404 when the name is not on the simulation", () => {
    try {
      assertOutputAccessible(SIM, "not_a_real_output");
      throw new Error("expected assertOutputAccessible to throw");
    } catch (err) {
      expect(isHttpError(err)).toBe(true);
      if (isHttpError(err)) expect(err.status).toBe(404);
    }
  });
});
