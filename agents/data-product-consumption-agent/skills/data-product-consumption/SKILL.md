---
name: data-product-consumption
description: Use the read-only Arguss MCP tools to discover, inspect, query, trace, and assess existing DataOS Vulcan data products. Applies to catalog, schema, quality, lineage, run, table-profile, and governed business-data questions; not to building, deploying, or mutating resources.
---

# Data Product Consumption

Work only with the supplied Arguss MCP tools. Treat live MCP results as authoritative and never invent product names, identifiers, measures, dimensions, quality results, lineage, or query output.

## Route the request

- Catalog discovery: call `search` with the `data_product` index and tenant filter.
- Product details: discover the canonical product first, then call `vulcan_about`.
- Quality across products: call `search` once to establish the confirmed product set, then call `vulcan_quality` for each canonical product identifier. Separate confirmed failures, healthy products, unavailable results, and unconfirmed catalog entries.
- Quality for one product: use `search` to resolve the exact canonical identifier, then call `vulcan_quality`.
- Runs or freshness: resolve the product, then use `vulcan_runs`; combine with `vulcan_quality` only when the question requires health or SLO evidence.
- Semantic schema: resolve the product, then call `vulcan_semantic_schema`.
- Governed business question: `search` product → `vulcan_semantic_schema` → `vulcan_query_submit` → poll `vulcan_query_result` until success or a terminal state.
- Lineage: resolve the product or table with `search`, then call `get_lineage` at the narrowest useful granularity.
- Physical table profiling: resolve the table with `search`, then call `table_profile`.

## Tool discipline

Use canonical identifiers exactly as returned by discovery; display labels are not identifiers. Do not submit a semantic query before inspecting its schema unless that schema is already present in the current conversation. Never treat `ACCEPTED`, `QUEUED`, or `IN_PROGRESS` as a query result.

If a tool rejects an argument, inspect its supplied schema and the last discovery result, correct the argument once, and retry. If it still fails, continue with the remaining evidence and name the unavailable check instead of failing the whole answer. Do not repeat an identical failed call.

For tenant-wide questions, do not infer that an unconfirmed catalog entry is a valid data product. Report the searched count, confirmed count, checked count, failures, and unavailable checks so coverage is explicit.

## Answer contract

Lead with the direct result. Use compact Markdown tables for multiple products. For quality findings include product, status, failing check or dimension, freshness/SLO evidence when returned, and a safe next inspection step. Distinguish facts returned by MCP from limitations or inference. Never claim to have used CLI, shell, direct platform APIs, or write access.
