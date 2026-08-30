import { env } from "$env/dynamic/private";
import { createTsdhnClient, type TsdhnClient } from "@tsdhn/api-client";

export function computeClient(fetch: typeof globalThis.fetch): TsdhnClient {
  if (!env.COMPUTE_API_URL) throw new Error("COMPUTE_API_URL is not set");
  if (!env.COMPUTE_API_TOKEN) throw new Error("COMPUTE_API_TOKEN is not set");
  return createTsdhnClient({
    baseUrl: env.COMPUTE_API_URL,
    computeApiToken: env.COMPUTE_API_TOKEN,
    fetch,
  });
}

export function computeRequestConfig(): { url: string; headers: Record<string, string> } {
  if (!env.COMPUTE_API_URL) throw new Error("COMPUTE_API_URL is not set");
  if (!env.COMPUTE_API_TOKEN) throw new Error("COMPUTE_API_TOKEN is not set");
  return {
    url: env.COMPUTE_API_URL.replace(/\/$/, ""),
    headers: { Authorization: `Bearer ${env.COMPUTE_API_TOKEN}` },
  };
}
