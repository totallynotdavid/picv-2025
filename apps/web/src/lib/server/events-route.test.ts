import { isHttpError } from "@sveltejs/kit";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  computeRequestConfig: vi.fn(),
  getSimulation: vi.fn(),
}));

vi.mock("$lib/server/compute-api", () => ({
  computeRequestConfig: mocks.computeRequestConfig,
}));
import { GET } from "../../routes/(app)/simulations/[id]/events/+server";

function context(overrides: Record<string, unknown> = {}) {
  return {
    params: { id: "sim-1" },
    locals: {
      user: { id: "user-1" },
      simulationRepository: { getSimulation: mocks.getSimulation },
    },
    fetch: vi.fn(),
    ...overrides,
  };
}

async function expectHttpError(action: unknown, status: number) {
  try {
    await action;
    throw new Error("expected handler to throw");
  } catch (caught) {
    expect(isHttpError(caught)).toBe(true);
    if (isHttpError(caught)) expect(caught.status).toBe(status);
  }
}

describe("simulation events route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.computeRequestConfig.mockReturnValue({
      url: "https://compute.example",
      headers: { authorization: "Bearer token" },
    });
  });

  it("rejects a simulation that has not reached the compute service", async () => {
    mocks.getSimulation.mockResolvedValue({ id: "sim-1", status: "submitting" });

    await expectHttpError(GET(context() as never), 409);
    expect(mocks.computeRequestConfig).not.toHaveBeenCalled();
  });

  it("returns a controlled gateway error when the upstream stream is unavailable", async () => {
    mocks.getSimulation.mockResolvedValue({ id: "sim-1", status: "running" });
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 503 }));

    await expectHttpError(GET(context({ fetch }) as never), 502);
  });

  it("requires an authenticated user before querying the simulation", async () => {
    await expectHttpError(GET(context({ locals: { user: null } }) as never), 401);

    expect(mocks.getSimulation).not.toHaveBeenCalled();
  });

  it("returns not found when the user cannot access the simulation", async () => {
    mocks.getSimulation.mockResolvedValue(undefined);

    await expectHttpError(GET(context() as never), 404);
    expect(mocks.computeRequestConfig).not.toHaveBeenCalled();
  });

  it("passes through a healthy upstream event stream with safe response headers", async () => {
    mocks.getSimulation.mockResolvedValue({ id: "sim-1", status: "running" });
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.close();
      },
    });
    const fetch = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));

    const response = await GET(context({ fetch }) as never);

    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(response.headers.get("cache-control")).toBe("no-cache");
    expect(response.body).toBe(body);
    expect(fetch).toHaveBeenCalledWith("https://compute.example/api/v1/jobs/sim-1/events", {
      headers: { authorization: "Bearer token" },
    });
  });
});
