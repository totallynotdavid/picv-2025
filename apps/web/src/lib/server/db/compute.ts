import { integer, jsonb, pgSchema, text, timestamp, uuid } from "drizzle-orm/pg-core";

/** Read-only Drizzle definitions for the compute service's job table. */
const computeSchema = pgSchema("compute");

export type ArtifactRef = {
  name: string;
  key: string;
  filename: string;
  content_type: string;
};

export const computeJob = computeSchema.table("jobs", {
  id: uuid("id").primaryKey(),
  externalId: uuid("external_id").notNull().unique(),
  status: text("status").notNull(),
  details: text("details"),
  step: text("step"),
  stepIndex: integer("step_index"),
  totalSteps: integer("total_steps"),
  calculation: jsonb("calculation"),
  travelTimes: jsonb("travel_times"),
  artifacts: jsonb("artifacts").$type<ArtifactRef[]>(),
  error: text("error"),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
});

export type ComputeJob = typeof computeJob.$inferSelect;
