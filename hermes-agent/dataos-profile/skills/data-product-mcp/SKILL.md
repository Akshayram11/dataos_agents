---
name: data-product-mcp
description: Query governed DataOS data products through their MCP.
version: 0.2.0
author: Akshay Chame
license: MIT
metadata:
  hermes:
    tags: [dataos, data-products, mcp]
    category: dataos
---

# Data Product MCP Skill

Use `mcp__dataproduct_mcp__*` for governed data-product discovery, quality,
lineage, semantic metadata, and consumption questions. It is not a DataOS
resource-runtime or deployment interface.

## When to Use

Use when an answer depends on cataloged data products or governed data rather
than the runtime state of a DataOS resource.

## Prerequisites

The `dataproduct-mcp` server must be connected using the DataOS API key saved
in the authenticated Keys UI. Do not request or echo the key in chat.

## Procedure

1. Confirm that `dataproduct-mcp` is in the active tool sources. Never use
   OAuth authorization for this bearer-token server.
2. Prove the connection with `search(index="data_product_search_index")`
   before making availability or completeness claims.
3. Identify the product with `search` before requesting its details.
4. Retrieve metadata, quality, or lineage evidence before answering trust or
   impact questions.
5. For quality across products, establish the confirmed product set with one
   search, then call the available quality tool for each canonical identifier.
6. For governed questions, inspect the semantic schema, submit the query, and
   retrieve its result using only tools exposed by this MCP.
7. Distinguish confirmed results from incomplete, paged, truncated, or
   unconfirmed search results.
8. State the MCP tools used without exposing headers or credentials.

## Pitfalls

- A configured server is not necessarily connected; perform the search probe.
- MCP additions require a gateway restart and a new chat session before their
  tools appear in the session inventory.
- Search results remain candidates until a detail tool confirms them.
- Do not use this MCP to infer DataOS runtime health; use `dataos-cli`.
- Never claim completeness when the server reports paging or truncation.

## Verification

The response identifies the live MCP tool evidence, what was confirmed, and
what remains unverified. Connection failures must include the returned HTTP or
protocol error without suggesting OAuth for this server.
