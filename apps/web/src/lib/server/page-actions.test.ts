import { isHttpError, isRedirect } from "@sveltejs/kit";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  computeClient: vi.fn(),
  submitSimulation: vi.fn(),
  createSimulation: vi.fn(),
  getSimulation: vi.fn(),
  message: vi.fn(),
  superValidate: vi.fn(),
  toEarthquakeInput: vi.fn(),
  zod4: vi.fn(),
}));

vi.mock("$lib/server/compute-api", () => ({ computeClient: mocks.computeClient }));
vi.mock("$lib/server/submit-simulation", () => ({
  submitSimulation: mocks.submitSimulation,
}));
vi.mock("$lib/schema/earthquake", () => ({
  defaultEarthquake: {},
  earthquakeSchema: {},
  toEarthquakeInput: mocks.toEarthquakeInput,
}));
vi.mock("sveltekit-superforms", () => ({
  message: mocks.message,
  superValidate: mocks.superValidate,
}));
vi.mock("sveltekit-superforms/adapters", () => ({ zod4: mocks.zod4 }));

import { actions as newActions } from "../../routes/(app)/new/+page.server";
import { actions as simulationActions } from "../../routes/(app)/simulations/[id]/+page.server";

const SIMULATION_ID = "11111111-1111-4111-8111-111111111111";
const INPUT = {
  Mw: 8.0,
  h: 12,
  lat0: -20.5,
  lon0: -70.5,
  dia: "30",
  hhmm: "0445",
};
const FORM = { valid: true, data: { magnitude: 8.0 } };
const SIM = {
  id: "sim-1",
  params: INPUT,
  status: "submission_failed",
};

function repository() {
  return {
    createSimulation: mocks.createSimulation,
    getSimulation: mocks.getSimulation,
  };
}

function newContext(overrides: Record<string, unknown> = {}) {
  return {
    request: new Request("https://web.example/new", { method: "POST" }),
    locals: { user: { id: "user-1" }, simulationRepository: repository() },
    fetch: vi.fn(),
    ...overrides,
  };
}

function retryContext(overrides: Record<string, unknown> = {}) {
  return {
    params: { id: "sim-1" },
    locals: { user: { id: "user-1" }, simulationRepository: repository() },
    fetch: vi.fn(),
    ...overrides,
  };
}

async function expectRedirect(action: unknown, location: string) {
  try {
    await action;
    throw new Error("expected action to redirect");
  } catch (caught) {
    expect(isRedirect(caught)).toBe(true);
    if (isRedirect(caught)) {
      expect(caught.status).toBe(303);
      expect(caught.location).toBe(location);
    }
  }
}

async function expectHttpError(action: unknown, status: number) {
  try {
    await action;
    throw new Error("expected action to throw");
  } catch (caught) {
    expect(isHttpError(caught)).toBe(true);
    if (isHttpError(caught)) expect(caught.status).toBe(status);
  }
}

describe("new simulation action", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubGlobal("crypto", { randomUUID: () => SIMULATION_ID });
    mocks.zod4.mockReturnValue("adapter");
    mocks.toEarthquakeInput.mockReturnValue(INPUT);
    mocks.superValidate.mockResolvedValue(FORM);
    mocks.createSimulation.mockResolvedValue(undefined);
    mocks.computeClient.mockReturnValue({});
    mocks.submitSimulation.mockResolvedValue({ ok: true });
    mocks.message.mockImplementation((form, text, options) => ({ form, text, options }));
  });

  it("persists and submits valid input before redirecting", async () => {
    await expectRedirect(
      newActions.default(newContext() as never),
      `/simulations/${SIMULATION_ID}`,
    );

    expect(mocks.createSimulation).toHaveBeenCalledWith({
      id: SIMULATION_ID,
      userId: "user-1",
      params: INPUT,
    });
    expect(mocks.submitSimulation).toHaveBeenCalledWith(
      { id: SIMULATION_ID, params: INPUT },
      expect.anything(),
      expect.objectContaining({ createSimulation: mocks.createSimulation }),
    );
  });

  it("does not create a simulation for invalid form data", async () => {
    mocks.superValidate.mockResolvedValue({ valid: false, errors: { magnitude: "bad" } });

    const result = await newActions.default(newContext() as never);

    expect(result).toMatchObject({ status: 400 });
    expect(mocks.createSimulation).not.toHaveBeenCalled();
    expect(mocks.submitSimulation).not.toHaveBeenCalled();
  });

  it("returns a form error when the compute service rejects valid input", async () => {
    mocks.submitSimulation.mockResolvedValue({ ok: false, error: "queue unavailable" });

    const result = await newActions.default(newContext() as never);

    expect(result).toEqual({
      form: FORM,
      text: "No se pudo iniciar la simulación.",
      options: { status: 502 },
    });
  });
});

describe("simulation retry action", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getSimulation.mockResolvedValue(SIM);
    mocks.computeClient.mockReturnValue({});
    mocks.submitSimulation.mockResolvedValue({ ok: true });
  });

  it("resubmits a simulation whose earlier submission failed", async () => {
    await expectRedirect(simulationActions.retry(retryContext() as never), "/simulations/sim-1");

    expect(mocks.getSimulation).toHaveBeenCalledWith("user-1", "sim-1");
    expect(mocks.submitSimulation).toHaveBeenCalledWith(
      SIM,
      expect.anything(),
      expect.objectContaining({ getSimulation: mocks.getSimulation }),
    );
  });

  it("does not contact compute for a non-retryable simulation", async () => {
    mocks.getSimulation.mockResolvedValue({ ...SIM, status: "running" });

    const result = await simulationActions.retry(retryContext() as never);

    expect(result).toMatchObject({ status: 400 });
    expect(mocks.computeClient).not.toHaveBeenCalled();
    expect(mocks.submitSimulation).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated retry", async () => {
    await expectHttpError(
      simulationActions.retry(retryContext({ locals: { user: null } }) as never),
      401,
    );
    expect(mocks.getSimulation).not.toHaveBeenCalled();
  });
});
