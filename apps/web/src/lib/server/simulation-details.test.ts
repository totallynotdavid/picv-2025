import { describe, expect, it } from "vitest";

import { toSimulationDetails } from "./simulation-details";

const BASE = {
  id: "sim-1",
  userId: "user-1",
  params: { Mw: 8.0 },
  createdAt: new Date("2026-01-01T00:00:00Z"),
  submissionError: null,
  computeStatus: null,
  details: null,
  step: null,
  stepIndex: null,
  totalSteps: null,
  calculation: null,
  travelTimes: null,
  computeError: null,
  outputs: null,
  startedAt: null,
  finishedAt: null,
};

describe("toSimulationDetails", () => {
  it("reports submitting before a compute row exists", () => {
    const details = toSimulationDetails(BASE);

    expect(details.status).toBe("submitting");
  });

  it("reports submission_failed when submission failed before a compute row exists", () => {
    const details = toSimulationDetails({
      ...BASE,
      submissionError: "compute service unreachable",
    });

    expect(details.status).toBe("submission_failed");
    expect(details.error).toBe("compute service unreachable");
  });

  it("prefers the live compute status once a compute row exists", () => {
    const details = toSimulationDetails({
      ...BASE,
      submissionError: "stale submission error",
      computeStatus: "running",
    });

    expect(details.status).toBe("running");
  });

  it("prefers the compute error over an earlier submission error", () => {
    const details = toSimulationDetails({
      ...BASE,
      submissionError: "stale submission error",
      computeStatus: "failed",
      computeError: "worker crashed",
    });

    expect(details.error).toBe("worker crashed");
  });

  it("uses the submission error when there is no compute row", () => {
    const details = toSimulationDetails({
      ...BASE,
      submissionError: "submission failed",
    });

    expect(details.error).toBe("submission failed");
  });

  it("maps stored outputs to names used by download links", () => {
    const details = toSimulationDetails({
      ...BASE,
      outputs: [
        { name: "max_height_map", contentType: "application/pdf" },
        { name: "mareogram", contentType: "image/svg+xml" },
      ],
    });

    expect(details.outputs).toEqual(["max_height_map", "mareogram"]);
  });

  it("defaults outputs to an empty list when the compute row has none", () => {
    const details = toSimulationDetails({ ...BASE, outputs: null });

    expect(details.outputs).toEqual([]);
  });
});
