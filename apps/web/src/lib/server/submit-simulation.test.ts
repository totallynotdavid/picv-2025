import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  clearSubmissionFailure: vi.fn(),
  recordSubmissionFailure: vi.fn(),
}));

import { submitSimulation } from "./submit-simulation";

const SIM = {
  id: "sim-1",
  params: { Mw: 8.0 },
  submissionError: "earlier failure",
};

function client() {
  return { POST: vi.fn() };
}

function repository() {
  return {
    clearSubmissionFailure: mocks.clearSubmissionFailure,
    recordSubmissionFailure: mocks.recordSubmissionFailure,
  };
}

describe("submitSimulation", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.clearSubmissionFailure.mockResolvedValue(undefined);
    mocks.recordSubmissionFailure.mockResolvedValue(undefined);
  });

  it("submits with the simulation id and clears an earlier failure", async () => {
    const api = client();
    api.POST.mockResolvedValue({ data: { simulation_id: "sim-1" }, error: undefined });

    await expect(submitSimulation(SIM, api as never, repository())).resolves.toEqual({ ok: true });

    expect(api.POST).toHaveBeenCalledWith("/api/v1/jobs", {
      body: { simulation_id: "sim-1", input: SIM.params },
    });
    expect(mocks.clearSubmissionFailure).toHaveBeenCalledWith("sim-1");
    expect(mocks.recordSubmissionFailure).not.toHaveBeenCalled();
  });

  it("does not update a new simulation after successful submission", async () => {
    const api = client();
    api.POST.mockResolvedValue({ data: { simulation_id: "sim-1" }, error: undefined });

    await expect(
      submitSimulation({ id: SIM.id, params: SIM.params }, api as never, repository()),
    ).resolves.toEqual({ ok: true });

    expect(mocks.clearSubmissionFailure).not.toHaveBeenCalled();
    expect(mocks.recordSubmissionFailure).not.toHaveBeenCalled();
  });

  it("records the compute API detail when submission is rejected", async () => {
    const api = client();
    api.POST.mockResolvedValue({
      data: undefined,
      error: { detail: "same simulation id has different input" },
    });

    await expect(submitSimulation(SIM, api as never, repository())).resolves.toEqual({
      ok: false,
      error: "same simulation id has different input",
    });

    expect(mocks.recordSubmissionFailure).toHaveBeenCalledWith(
      "sim-1",
      "same simulation id has different input",
    );
  });

  it("records transport failures for the researcher", async () => {
    const api = client();
    api.POST.mockRejectedValue(new Error("compute unavailable"));

    await expect(submitSimulation(SIM, api as never, repository())).resolves.toEqual({
      ok: false,
      error: "compute unavailable",
    });

    expect(mocks.recordSubmissionFailure).toHaveBeenCalledWith("sim-1", "compute unavailable");
  });
});
