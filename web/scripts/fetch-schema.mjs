#!/usr/bin/env node
/**
 * pnpm api:schema — put the backend OpenAPI document into openapi/schema.json.
 *
 * 1. Prefer a live backend: GET http://localhost:8000/api/schema/?format=json
 * 2. Fallback: convert ../docs/openapi.json (YAML despite the .json extension).
 */
import { writeFileSync, readFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
const out = join(root, '..', 'openapi', 'schema.json')
mkdirSync(dirname(out), { recursive: true })

async function fromBackend() {
  try {
    const res = await fetch('http://localhost:8000/api/schema/?format=json', {
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function fromDocsFile() {
  // root is <repo>/web/scripts — the repo docs/ dir is two levels up.
  const docs = join(root, '..', '..', 'docs', 'openapi.json')
  if (!existsSync(docs)) return null
  const yaml = await import('js-yaml')
  return yaml.load(readFileSync(docs, 'utf8'))
}

const schema = (await fromBackend()) ?? (await fromDocsFile())
if (!schema) {
  console.error('No schema source: backend is down and docs/openapi.json is missing.')
  process.exit(1)
}
writeFileSync(out, JSON.stringify(schema, null, 2) + '\n')
console.log(`openapi/schema.json written (${Object.keys(schema.paths ?? {}).length} paths)`)
