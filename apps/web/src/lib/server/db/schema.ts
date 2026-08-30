import { relations, sql } from "drizzle-orm";
import { index, jsonb, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";

import { user } from "./auth.schema";

/** Web-owned request data. Live execution state stays in `compute.jobs`. */
export const simulation = pgTable(
  "simulation",
  {
    id: uuid("id").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    params: jsonb("params").notNull(),
    /** Whether the compute service accepted the request. */
    dispatchStatus: text("dispatch_status").notNull().default("pending"),
    dispatchError: text("dispatch_error"),
    computeBackend: text("compute_backend"),
    computeJobId: text("compute_job_id"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .default(sql`now()`)
      .notNull(),
    dispatchedAt: timestamp("dispatched_at", { withTimezone: true }),
  },
  (table) => [
    index("simulation_user_created_at_idx").on(table.userId, table.createdAt.desc()),
    index("simulation_dispatch_status_idx").on(table.dispatchStatus),
  ],
);

export const simulationRelations = relations(simulation, ({ one }) => ({
  user: one(user, {
    fields: [simulation.userId],
    references: [user.id],
  }),
}));

export type Simulation = typeof simulation.$inferSelect;
export type NewSimulation = typeof simulation.$inferInsert;

export * from "./auth.schema";
