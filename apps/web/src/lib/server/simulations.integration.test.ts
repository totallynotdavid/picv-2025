import { randomUUID } from "node:crypto";

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import * as schema from "./db/schema";
import { createSimulationRepository } from "./simulation-repository";

const databaseUrl = process.env.DATABASE_URL;

describe("simulation repository", () => {
  let client: ReturnType<typeof postgres>;
  let repository: ReturnType<typeof createSimulationRepository>;

  beforeAll(() => {
    if (!databaseUrl) {
      throw new Error("DATABASE_URL is not set; run `mise run test-integration`");
    }
    client = postgres(databaseUrl, { max: 2 });
    repository = createSimulationRepository(drizzle(client, { schema }));
  });

  afterAll(async () => {
    await client.end();
  });

  it("keeps simulation reads scoped to the owning user", async () => {
    const ownerId = randomUUID();
    const otherUserId = randomUUID();
    const ownerSimulationId = randomUUID();
    const otherSimulationId = randomUUID();

    await client`
      INSERT INTO "user" ("id", "name", "email")
      VALUES (${ownerId}, 'Owner', ${`${ownerId}@example.test`}),
             (${otherUserId}, 'Other', ${`${otherUserId}@example.test`})
    `;

    await repository.createSimulation({
      id: ownerSimulationId,
      userId: ownerId,
      params: { Mw: 8.0 },
    });
    await repository.createSimulation({
      id: otherSimulationId,
      userId: otherUserId,
      params: { Mw: 7.5 },
    });

    const ownerDetails = await repository.getSimulation(ownerId, ownerSimulationId);

    expect(ownerDetails).toMatchObject({
      id: ownerSimulationId,
      userId: ownerId,
      status: "submitting",
      outputs: [],
    });
    await expect(repository.getSimulation(otherUserId, ownerSimulationId)).resolves.toBeUndefined();
    await expect(repository.getSimulation(ownerId, otherSimulationId)).resolves.toBeUndefined();
    await expect(repository.listSimulations(ownerId)).resolves.toHaveLength(1);
  });

  it("records and clears submission failures", async () => {
    const userId = randomUUID();
    const simulationId = randomUUID();

    await client`
      INSERT INTO "user" ("id", "name", "email")
      VALUES (${userId}, 'Submitter', ${`${userId}@example.test`})
    `;
    await repository.createSimulation({
      id: simulationId,
      userId,
      params: { Mw: 8.0 },
    });

    await repository.recordSubmissionFailure(simulationId, "queue unavailable");
    await expect(repository.getSimulation(userId, simulationId)).resolves.toMatchObject({
      status: "submission_failed",
      submissionError: "queue unavailable",
    });

    await repository.clearSubmissionFailure(simulationId);
    await expect(repository.getSimulation(userId, simulationId)).resolves.toMatchObject({
      status: "submitting",
      submissionError: null,
    });
  });
});
