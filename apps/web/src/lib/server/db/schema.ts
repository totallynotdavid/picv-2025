import { relations, sql } from "drizzle-orm";
import { index, jsonb, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";

import { user } from "./auth.schema";

export const simulation = pgTable(
  "simulation",
  {
    id: uuid("id").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => user.id, { onDelete: "cascade" }),
    params: jsonb("params").notNull(),
    submissionError: text("submission_error"),
    createdAt: timestamp("created_at", { withTimezone: true })
      .default(sql`now()`)
      .notNull(),
  },
  (table) => [index("simulation_user_created_at_idx").on(table.userId, table.createdAt.desc())],
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
