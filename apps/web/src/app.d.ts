import type { User, Session } from "better-auth";

import type { SimulationRepository } from "$lib/server/simulation-repository";

declare global {
  namespace App {
    interface Locals {
      user?: User;
      session?: Session;
      simulationRepository: SimulationRepository;
    }
  }
}

export {};
