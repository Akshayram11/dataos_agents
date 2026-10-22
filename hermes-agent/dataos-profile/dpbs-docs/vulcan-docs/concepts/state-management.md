---
description: >-
  How Vulcan remembers what it has already done: the PostgreSQL state store, the
  object store cache, and the two Secrets that connect them.
hidden: true
noIndex: true
---

# State management

Vulcan keeps a record of the current state of a project. It is Vulcan's memory: it records what has already happened, what is currently active, and what needs to change next. This is what lets Vulcan detect real changes without re-comparing an entire project, avoid repeating work it has already done, and apply updates safely across environments.

That state is not held in the project files. It lives in two backing stores that Vulcan connects to at runtime:

* **PostgreSQL state store:** the project state itself, such as fingerprints, plans, environments, and versions.
* **Object store:** cached query outputs, so results can be reused instead of recomputed.

Both are provisioned as part of Data Plane infrastructure setup, and Vulcan reads their connection details from two Secrets in the Tenant.

## PostgreSQL state store

The PostgreSQL state store is where Vulcan tracks the current state of the project. It can hold information such as:

* Which models or queries have already been processed
* Which version of a model is currently active
* What changed between the previous run and the current run
* Which environments exist, such as development, staging, or production
* What data intervals or time ranges have already been loaded
* Which cached or generated outputs are connected to the current project state

The database itself is the PostgreSQL instance provisioned for the Data Plane: Amazon RDS on AWS, Azure Database for PostgreSQL on Azure.

## Object store

The object store is where Vulcan saves cached query outputs. When a query runs, Vulcan generates result files that can be reused later. Instead of running the same query again, Vulcan reads the saved results from the object store. This reduces compute cost, improves response time, and makes results available across users and environments.

Vulcan supports Amazon S3, Azure Blob Storage, and Google Cloud Storage as object store backends.

## Configure the connections

Vulcan receives the connection details for both stores through two Secrets. Your SRE creates the Vulcan state Secret and the object store connection Secret in the `system` Tenant, so there is no manifest to apply from a Vulcan project.

{% hint style="info" %}
**The Secret names are defaults, not fixed requirements**

`vulcan-state-connection` and `vulcan-object-store-connection` are the names Vulcan falls back to when nothing else is set. A project can point at differently named Secrets through `state_store_connection` and `object_store_connection` in its deployment configuration. See [Deployment](../deployment.md).
{% endhint %}

{% hint style="info" %}
Both Secrets are Tenant-scoped. Every Tenant has its own pair; they are not shared or inherited across Tenants.
{% endhint %}

The manifests below are here so you know what Vulcan reads at runtime.

### PostgreSQL state store Secret

```yaml
name: vulcan-state-connection
version: v2alpha
type: secret
layer: user
secret:
  type: key-value
  data:
    USERNAME: "${{ POSTGRES_USERNAME }}"
    PASSWORD: "${{ POSTGRES_PASSWORD }}"
    HOST: "${{ POSTGRES_HOST }}"
    PORT: "5432"
    DATABASE: "${{ POSTGRES_DATABASE }}"
```

<table><thead><tr><th width="180">Field</th><th>Description</th></tr></thead><tbody><tr><td><code>USERNAME</code></td><td>User that Vulcan connects to the state database as.</td></tr><tr><td><code>PASSWORD</code></td><td>Password for that user.</td></tr><tr><td><code>HOST</code></td><td>Hostname or endpoint of the PostgreSQL instance provisioned for the Data Plane.</td></tr><tr><td><code>PORT</code></td><td>Port the instance listens on, <code>5432</code> unless it was changed.</td></tr><tr><td><code>DATABASE</code></td><td>Database Vulcan writes its state to.</td></tr></tbody></table>

### Object store Secret

Choose the configuration corresponding to your object store and create the Secret using the applicable manifest.

{% tabs %}
{% tab title="Amazon S3" %}
```yaml
name: vulcan-object-store-connection
version: v2alpha
type: secret
layer: user
secret:
  type: key-value
  data:
    STORAGE_FORMAT: "s3"
    AWS_ACCESS_KEY: "${{ ACCESS_KEY }}"
    AWS_SECRET_KEY: "${{ SECRET_KEY }}"
    BUCKET: "${{ BUCKET_NAME }}"
    RELATIVE_PATH: "dataos-state-store"
    AWS_ENDPOINT: "https://s3.${{ REGION }}.amazonaws.com"
    AWS_REGION: "${{ REGION }}"
```

<table><thead><tr><th width="200">Field</th><th>Description</th></tr></thead><tbody><tr><td><code>STORAGE_FORMAT</code></td><td>Backend type, <code>s3</code>.</td></tr><tr><td><code>AWS_ACCESS_KEY</code></td><td>Access key of the IAM identity with read and write access to the bucket.</td></tr><tr><td><code>AWS_SECRET_KEY</code></td><td>Secret key for that identity.</td></tr><tr><td><code>BUCKET</code></td><td>Bucket holding the cached outputs.</td></tr><tr><td><code>RELATIVE_PATH</code></td><td>Path within the bucket that Vulcan writes under.</td></tr><tr><td><code>AWS_ENDPOINT</code></td><td>S3 endpoint for the bucket's region.</td></tr><tr><td><code>AWS_REGION</code></td><td>Region the bucket lives in.</td></tr></tbody></table>
{% endtab %}

{% tab title="Azure Blob Storage (key)" %}
```yaml
name: vulcan-object-store-connection
version: v2alpha
type: secret
layer: user
secret:
  type: key-value
  data:
    STORAGE_FORMAT: "azure"
    RELATIVE_PATH: "${{ RELATIVE_PATH }}"
    AZURE_CONTAINER: "${{ CONTAINER_NAME }}"
    AZURE_STORAGE_ACCOUNT: "${{ STORAGE_ACCOUNT_NAME }}"
    AZURE_STORAGE_KEY: "${{ STORAGE_ACCOUNT_KEY }}"
    AZURE_ENDPOINT_SUFFIX: "blob.core.windows.net"  # Optional; used verbatim as <account>.<suffix>
```

<table><thead><tr><th width="240">Field</th><th>Description</th></tr></thead><tbody><tr><td><code>STORAGE_FORMAT</code></td><td>Backend type, <code>azure</code>.</td></tr><tr><td><code>RELATIVE_PATH</code></td><td>Path within the container that Vulcan writes under.</td></tr><tr><td><code>AZURE_CONTAINER</code></td><td>Blob container holding the cached outputs.</td></tr><tr><td><code>AZURE_STORAGE_ACCOUNT</code></td><td>Storage account the container belongs to.</td></tr><tr><td><code>AZURE_STORAGE_KEY</code></td><td>Access key for that storage account.</td></tr></tbody></table>
{% endtab %}

{% tab title="Azure Blob Storage (service principal)" %}
```yaml
name: vulcan-object-store-connection
version: v2alpha
type: secret
layer: user
secret:
  type: key-value
  data:
    STORAGE_FORMAT: "azure"
    RELATIVE_PATH: "${{ RELATIVE_PATH }}"
    AZURE_CONTAINER: "${{ CONTAINER_NAME }}"
    AZURE_STORAGE_ACCOUNT: "${{ STORAGE_ACCOUNT_NAME }}"
    AZURE_TENANT_ID: "${{ TENANT_ID }}"
    AZURE_CLIENT_ID: "${{ CLIENT_ID }}"
    AZURE_CLIENT_SECRET: "${{ CLIENT_SECRET }}"
    AZURE_ENDPOINT_SUFFIX: "blob.core.windows.net"  # Optional; used verbatim as <account>.<suffix>
```

<table><thead><tr><th width="240">Field</th><th>Description</th></tr></thead><tbody><tr><td><code>STORAGE_FORMAT</code></td><td>Backend type, <code>azure</code>.</td></tr><tr><td><code>RELATIVE_PATH</code></td><td>Path within the container that Vulcan writes under.</td></tr><tr><td><code>AZURE_CONTAINER</code></td><td>Blob container holding the cached outputs.</td></tr><tr><td><code>AZURE_STORAGE_ACCOUNT</code></td><td>Storage account the container belongs to.</td></tr><tr><td><code>AZURE_TENANT_ID</code></td><td>Entra ID tenant the service principal is registered in.</td></tr><tr><td><code>AZURE_CLIENT_ID</code></td><td>Application ID of the service principal.</td></tr><tr><td><code>AZURE_CLIENT_SECRET</code></td><td>Client secret for that service principal.</td></tr></tbody></table>
{% endtab %}

{% tab title="Google Cloud Storage" %}
```yaml
name: vulcan-object-store-connection
version: v2alpha
type: secret
layer: user
secret:
  type: key-value
  data:
    STORAGE_FORMAT: "gcs"
    RELATIVE_PATH: "${{ RELATIVE_PATH }}"
    BUCKET: "${{ BUCKET_NAME }}"
    GCS_PROJECT_ID: "${{ GCP_PROJECT_ID }}"
    GCS_ENDPOINT: "https://storage.googleapis.com"  # Optional
    GCS_CREDENTIALS_FILE: |
      {
        "type": "service_account",
        "project_id": "${{ GCP_PROJECT_ID }}",
        "private_key_id": "${{ PRIVATE_KEY_ID }}",
        "private_key": "${{ PRIVATE_KEY }}",
        "client_email": "${{ SERVICE_ACCOUNT_EMAIL }}",
        "client_id": "${{ CLIENT_ID }}",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "${{ CLIENT_X509_CERT_URL }}",
        "universe_domain": "googleapis.com"
      }
```

<table><thead><tr><th width="240">Field</th><th>Description</th></tr></thead><tbody><tr><td><code>STORAGE_FORMAT</code></td><td>Backend type, <code>gcs</code>.</td></tr><tr><td><code>RELATIVE_PATH</code></td><td>Path within the bucket that Vulcan writes under.</td></tr><tr><td><code>BUCKET</code></td><td>Bucket holding the cached outputs.</td></tr><tr><td><code>GCS_PROJECT_ID</code></td><td>Google Cloud project the bucket belongs to.</td></tr><tr><td><code>GCS_CREDENTIALS_FILE</code></td><td>Service account key JSON for an account with read and write access to the bucket.</td></tr></tbody></table>
{% endtab %}
{% endtabs %}

{% hint style="info" %}
These examples show all supported sources together for reference. Use separate manifests when configuring different object stores.
{% endhint %}

{% hint style="info" %}
Your SRE  creates both of them in the `system` Tenant. If Vulcan cannot reach its state store, raise it with them.
{% endhint %}

## Where to go next

* [Provision Data Plane](https://v2.dataos.info/operate/operator/provision-data-plane) - where the PostgreSQL instance and object store come from in the first place.
* [Run and plan](run-and-plan/README.md) - how Vulcan uses this state to decide what changed and what to execute.
