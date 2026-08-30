import { isHttpError } from "@sveltejs/kit";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  computeClient: vi.fn(),
}));

vi.mock("$lib/server/compute-api", () => ({ computeClient: mocks.computeClient }));

import { POST } from "../../routes/api/calculations/+server";

function context(overrides: Record<string, unknown> = {}) {
  return {
    request: new Request("https://web.example/api/calculations", {
      method: "POST",
      body: JSON.stringify({ Mw: 8.0 }),
    }),
    locals: { user: { id: "user-1" } },
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

describe("calculation preview route", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("requires a signed-in user before contacting the compute service", async () => {
    await expectHttpError(POST(context({ locals: { user: null } }) as never), 401);
    expect(mocks.computeClient).not.toHaveBeenCalled();
  });

  it("forwards the form body and returns the compute preview", async () => {
    const client = { POST: vi.fn() };
    const preview = { calculation: { length: 1 }, travel_times: { arrival_times: {} } };
    client.POST.mockResolvedValue({ data: preview, error: undefined });
    mocks.computeClient.mockReturnValue(client);

    const response = await POST(context() as never);

    expect(await response.json()).toEqual(preview);
    expect(client.POST).toHaveBeenCalledWith("/api/v1/calculations", {
      body: { Mw: 8.0 },
    });
  });

  it("returns a controlled gateway error when the compute preview fails", async () => {
    const client = { POST: vi.fn() };
    client.POST.mockResolvedValue({ data: undefined, error: { detail: "failed" } });
    mocks.computeClient.mockReturnValue(client);

    await expectHttpError(POST(context() as never), 502);
  });
});
