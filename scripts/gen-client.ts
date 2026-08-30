#!/usr/bin/env bun
import { $ } from 'bun';

const SCHEMA_JSON = 'libs/api-client/openapi.json';
const TYPES_OUT = 'libs/api-client/src/generated/schema.ts';

console.log('→ exporting OpenAPI schema from FastAPI…');
const openapi = await $`uv run python scripts/export_openapi.py`.text();
await Bun.write(SCHEMA_JSON, openapi);

console.log('→ generating TypeScript types…');
await $`bun x openapi-typescript ${SCHEMA_JSON} -o ${TYPES_OUT}`;

console.log(`✓ wrote ${TYPES_OUT}`);
