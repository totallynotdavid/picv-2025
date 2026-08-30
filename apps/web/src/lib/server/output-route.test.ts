import { isHttpError } from "@sveltejs/kit";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  computeRequestConfig: vi.fn(),
  getSimulation: vi.fn(),
}));

vi.mock("$lib/server/compute-api", () => ({
  computeRequestConfig: mocks.computeRequestConfig,
}));
import { GET } from "../../routes/(app)/simulations/[id]/outputs/[name]/+server";

const SIM = { id: "sim-1", outputs: ["max_height_map"] };

function context(overrides: Record<string, unknown> = {}) {
  return {
    params: { id: "sim-1", name: "max_height_map" },
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

describe("output download route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getSimulation.mockResolvedValue(SIM);
    mocks.computeRequestConfig.mockReturnValue({
      url: "https://compute.example",
      headers: { authorization: "Bearer token" },
    });
  });

  it("requires an authenticated user before querying the simulation", async () => {
    await expectHttpError(GET(context({ locals: { user: null } }) as never), 401);

    expect(mocks.getSimulation).not.toHaveBeenCalled();
  });

  it("returns not found without contacting compute for an unknown simulation", async () => {
    mocks.getSimulation.mockResolvedValue(undefined);

    await expectHttpError(GET(context() as never), 404);

    expect(mocks.computeRequestConfig).not.toHaveBeenCalled();
  });

  it("returns a controlled gateway error when compute does not redirect", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    const requestContext = context({ fetch });

    await expectHttpError(GET(requestContext as never), 502);
  });

  it("redirects the browser after ownership and output checks", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: { location: "https://minio.example/result.pdf" },
      }),
    );
    const requestContext = context({ fetch });

    try {
      await GET(requestContext as never);
      throw new Error("expected redirect");
    } catch (redirect) {
      expect(redirect).toMatchObject({
        status: 302,
        location: "https://minio.example/result.pdf",
      });
    }

    expect(mocks.getSimulation).toHaveBeenCalledWith("user-1", "sim-1");
    expect(fetch).toHaveBeenCalledWith(
      "https://compute.example/api/v1/jobs/sim-1/outputs/max_height_map",
      { headers: { authorization: "Bearer token" }, redirect: "manual" },
    );
  });
});
