import createClient, { type Client } from "openapi-fetch";
import type { paths } from "./generated/schema";

export type * from "./generated/schema";

export interface TsdhnClientOptions {
  baseUrl: string;
  computeApiToken: string;
  fetch?: typeof globalThis.fetch;
}

/** Server-only client for authenticated compute API requests. */
export function createTsdhnClient(options: TsdhnClientOptions): Client<paths> {
  return createClient<paths>({
    baseUrl: options.baseUrl,
    fetch: options.fetch,
    headers: { Authorization: `Bearer ${options.computeApiToken}` },
  });
}

export type TsdhnClient = Client<paths>;
