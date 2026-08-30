# @tsdhn/api-client

`@tsdhn/api-client` is generated from the compute API's OpenAPI definition.
The SvelteKit server is its only consumer.

The client sends `COMPUTE_API_TOKEN` with every authenticated request. Use it
only in server code; importing it into browser code could expose the token.

## Files

| File                      | Purpose                                                            |
| ------------------------- | ------------------------------------------------------------------ |
| `openapi.json`            | OpenAPI definition exported from FastAPI                           |
| `src/generated/schema.ts` | Generated TypeScript paths and schemas                             |
| `src/index.ts`            | Small `openapi-fetch` wrapper that adds compute API authentication |

## Usage

```ts
import { createTsdhnClient } from "@tsdhn/api-client";

const client = createTsdhnClient({
  baseUrl: process.env.COMPUTE_API_URL!,
  computeApiToken: process.env.COMPUTE_API_TOKEN!,
});
```

## Regenerate

After changing a FastAPI route or schema:

```sh
mise run gen-client
```

The command exports the FastAPI schema to `openapi.json`, then generates
`src/generated/schema.ts`. Do not edit either generated output by hand.

Route behavior belongs to the compute API and is visible in its OpenAPI UI.
This package owns only the generated TypeScript representation and the
server-only client wrapper.
