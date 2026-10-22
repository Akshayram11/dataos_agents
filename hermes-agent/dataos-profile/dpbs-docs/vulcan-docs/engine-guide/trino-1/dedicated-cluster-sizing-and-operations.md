---
description: >-
  Configure fixed worker capacity, write targets, fault handling, and JVM memory
  for dedicated Trino.
---

# Dedicated cluster sizing and operations

## Dedicated cluster sizing and operations

Use these requirements when Vulcan provisions a dedicated Trino cluster.

### Set fixed worker capacity

Cluster autoscaling is not available. The deployment accepts autoscaling settings but does not render them.

Set a fixed worker count with `spec.trino.workers.replicas`.

### Choose the materialization target

Materialized output lands in the first depot listed in `spec.depots[]`. Order this list deliberately. Place the writable materialization depot first.

### Fault tolerance

Fault-tolerant execution is unavailable in the reference deployment. A Trino retry policy requires an exchange manager. The reference deployment does not include one.

### Set JVM heap explicitly

Set `-Xmx` explicitly for coordinators and workers. Size it for the pod memory limit.

Without an explicit heap, workers can run out of memory or fail to register.
