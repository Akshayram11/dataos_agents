---
description: Constraints for Vulcan Spark and Iceberg lakehouse workloads.
---

# Spark lakehouse limitations

## Spark lakehouse limitations

Use this reference for the Vulcan Spark and Iceberg lakehouse path.

### Views

Views are not supported. `kind VIEW` does not work on this path.

Use `kind FULL` for every staging or intermediate layer that would otherwise be a view. Materialized views are not supported either. No separate materialized path exists. Use `kind FULL` as the materialized equivalent.

### Catalogs

Define all models under one catalog. Multi-catalog federation is not supported.

### Concurrent writers

Iceberg commits use optimistic concurrency. Concurrent writers can conflict.

Set `concurrencyPolicy: Forbid` and stagger heavy writers.

### Unique-key upserts

Unique-key upserts require the Iceberg storage format:

```
physical_properties(format = 'iceberg')
```

Without this setting, models insert rows instead of upserting them.

### Serving workloads

This path is not a low-latency serving engine. API queries trigger Spark jobs.

Pre-aggregate data for sub-second surfaces.
