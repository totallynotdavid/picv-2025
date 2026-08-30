import { isHttpError } from "@sveltejs/kit";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  computeClient: vi.fn(),
  submitSimulation: vi.fn(),
  listSimulations: vi.fn(),
  getSimulation: vi.fn(),
}));

vi.mock("$lib/server/compute-api", () => ({ computeClient: mocks.computeClient }));
vi.mock("$lib/server/submit-simulation", () => ({
  submitSimulation: mocks.submitSimulation,
}));

import { load as dashboardLoad } from "./(app)/dashboard/+page.server";
import { load as simulationLoad } from "./(app)/simulations/[id]/+page.server";

async function expectHttpError(action: unknown, status: number) {
  try {
    await action;
    throw new Error("expected load to throw");
  } catch (caught) {
    expect(isHttpError(caught)).toBe(true);
    if (isHttpError(caught)) expect(caught.status).toBe(status);
  }
}

function context(overrides: Record<string, unknown> = {}) {
  return {
    params: { id: "sim-1" },
    locals: {
      user: { id: "user-1" },
      simulationRepository: {
        listSimulations: mocks.listSimulations,
        getSimulation: mocks.getSimulation,
      },
    },
    ...overrides,
  };
}

describe("dashboard load", () => {
  beforeEach(() => vi.resetAllMocks());

  it("requires authentication before reading simulations", async () => {
    await expectHttpError(dashboardLoad({ locals: { user: null } } as never), 401);

    expect(mocks.listSimulations).not.toHaveBeenCalled();
  });

  it("returns only the signed-in user's simulations", async () => {
    const simulations = [{ id: "sim-1" }];
    mocks.listSimulations.mockResolvedValue(simulations);

    const result = await dashboardLoad(context() as never);

    expect(result).toEqual({ simulations });
    expect(mocks.listSimulations).toHaveBeenCalledWith("user-1");
  });
});

describe("simulation detail load", () => {
  beforeEach(() => vi.resetAllMocks());

  it("returns the owned simulation", async () => {
    const simulation = { id: "sim-1", status: "running" };
    mocks.getSimulation.mockResolvedValue(simulation);

    const result = await simulationLoad(context() as never);

    expect(result).toEqual({ sim: simulation });
    expect(mocks.getSimulation).toHaveBeenCalledWith("user-1", "sim-1");
  });

  it("returns not found when the simulation is not owned by the user", async () => {
    mocks.getSimulation.mockResolvedValue(undefined);

    await expectHttpError(simulationLoad(context() as never), 404);
  });
});
