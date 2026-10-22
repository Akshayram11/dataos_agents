---
description: >-
  Provision DataOS, lakehouse, compute, state-store, storage, and Git access for
  Spark deployments.
---

# Permissions and grants

This is the authorize stage: the step before you touch a gateway config or write a model. Provision the platform resources, object-storage grants, and DataOS access before you deploy a Vulcan Data Product using Spark.

### Platform dependencies <a href="#platform-dependencies" id="platform-dependencies"></a>

RequirementNotes

Spark-capable compute pool

Verify with `dataos-ctl resource -t compute get -a`; set `spec.compute` to this pool name.

Tenant-level `vulcan-spark` stack

Provides the runtime image, serving sidecars, dependency loading, and catalog templating.

DataOS lakehouse resource

Backed by S3 or ABFSS object storage.

Lakehouse depot

Attached as `dataos://<depot>?purpose=rw` in the Vulcan resource.

External Postgres for Vulcan state

Provisioned and wired automatically by the platform in production; nothing to add to project `config.yaml`.

Object-storage credentials

Stored on the lakehouse/depot, never hard-coded in project code.

Git-sync secret

Used by the Vulcan resource to pull model code.

Three roles are required: an admin role (platform SRE provisions the compute pool, installs the stack, creates the lakehouse and depot), the Vulcan service role (the `runAsUser`; runs Spark jobs and writes Iceberg tables through the lakehouse depot), and a consumer role (read-only via API endpoints).

Minimum object-storage grants:

<a class="button secondary">Ask</a><a class="button secondary">Copy</a>

```
S3:         s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket on the warehouse bucket
ABFSS:  Storage Blob Data Contributor on the container; Storage Account Key or SPN credentials on the depot
```

#### &#x20;<a href="#dataos-permissions" id="dataos-permissions"></a>

<br>

### Platform dependencies

Complete platform provisioning first.

Spark on Vulcan needs platform resources that an SRE team provisions before you write any model code. These resources provide the Spark runtime, Iceberg storage, state store, and source-code access.

| Requirement                        | Notes                                                                                         |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| Spark-capable compute pool         | Verify with `dataos-ctl resource -t compute get -a`. Set `spec.compute` to this pool name.    |
| Tenant-level `vulcan-spark` stack  | Provides the runtime image, serving sidecars, dependency loading, and catalog templating.     |
| DataOS lakehouse resource          | Backed by S3 or ABFSS object storage.                                                         |
| Lakehouse depot                    | Attach as `dataos://<depot>?purpose=rw` in the Vulcan resource.                               |
| External Postgres for Vulcan state | The platform provisions and wires this in production. Do not add it to project `config.yaml`. |
| Object-storage credentials         | Store these on the lakehouse or depot. Never hard-code them in project code.                  |
| Git-sync secret                    | Lets the Vulcan resource pull model code.                                                     |

The three roles below separate platform administration, workload execution, and consumer access.

| Role                | Responsibilities                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| Admin role          | Platform SRE provisions the compute pool, installs the stack, and creates the lakehouse and depot. |
| Vulcan service role | Configure as `runAsUser`. Runs Spark jobs and writes Iceberg tables through the lakehouse depot.   |
| Consumer role       | Provides read-only access through API endpoints.                                                   |

The lakehouse depot owns storage credentials. Grant the required cloud access to its backing storage.

| Storage | Required access                                                                                                |
| ------- | -------------------------------------------------------------------------------------------------------------- |
| S3      | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, and `s3:ListBucket` on the warehouse bucket.                |
| ABFSS   | **Storage Blob Data Contributor** on the container. Store Storage Account Key or SPN credentials on the depot. |

### DataOS permissions

After platform provisioning is complete, grant the following DataOS permissions:

| **Permission**                                                   | **What it Allows**                                                                                                                                                                                                      | **Granted By**                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **Tenant Access**                                                | Build and manage Data Products within your tenant.                                                                                                                                                                      | Tenant Admin                                                             |
| **`roles:id:data-dev`** _(or your tenant's equivalent role tag)_ | Create and apply Vulcan resources. Verify your role using `dataos-ctl user get` (check the **TAGS** column).                                                                                                            | Tenant Admin                                                             |
| **`depot:rw:<lakehouse-depot-name>`**                            | Read and write access to the lakehouse depot.                                                                                                                                                                           | Tenant Admin or Data Admin                                               |
| **`depot:r:<lakehouse-depot-name>`**                             | Read-only access to the lakehouse depot (for consumers).                                                                                                                                                                | Tenant Admin or Data Admin                                               |
| **Can Use** _(Compute, Depots, Secrets)_                         | Allows you to actually use Compute, Depots, and Secrets. **Note:** Resource access is deny-by-default. Even if you have a role tag or depot permission, you also need **Can Use** to use the resource.                  | Tenant Admin or Data Admin                                               |
| **`git-sync` Secret**                                            | Allows Vulcan to pull model code from Git using credentials stored in a Secret. Request a **git-sync Secret**, not raw Git credentials. If you create the Secret yourself, you still need **Can Use** permission on it. | Tenant Admin, Data Admin, or the Secret owner (with **Can Use** granted) |

Run `dataos-ctl get depot` to confirm your read access before you start. If the lakehouse depot is missing, request `depot:r` from your operator.

### Python version

Local development requires Python 3.10 (`python --version` must report `3.10.x`). The Spark runtime inside the Vulcan image manages its own Python version.

## Next steps

With access and platform resources ready, configure your gateway in [connection-options.md](connection-options.md "mention").
