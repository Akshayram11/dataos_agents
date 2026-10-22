---
description: Connect Vulcan to Snowflake using direct authentication or a DataOS Depot.
---

# Connect to Snowflake

With roles and grants in place from [permissions-and-grants.md](permissions-and-grants.md "mention"), this is the connect stage: configure the gateway that lets Vulcan reach Snowflake, then validate it before you write a single model. Connect Vulcan to Snowflake directly or through a DataOS Depot.

## Connection options

A direct connection supports four authentication methods. A DataOS Depot manages credentials and access purpose. Local development and quick tests typically use a direct connection; production deployments should move to a DataOS Depot (see Use a DataOS Depot below).

### Provide Snowflake connection details directly

Set connection details under `gateways.<name>.connection` in `config.yaml`.

* Key-pair JWT: set `authenticator: snowflake_jwt`, `private_key_path`, and `private_key_passphrase`.
* Username and password: set `user` and `password`.
* OAuth 2.0: set `token`.
* External-browser SSO: set `authenticator: externalbrowser`.

#### Example gateway configuration

{% tabs %}
{% tab title="JWT" %}
```yaml
gateways:
  default:
    connection:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT', '') }}"
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', '') }}"
      database: "{{ env_var('SNOWFLAKE_DATABASE', '') }}"
      role: "{{ env_var('SNOWFLAKE_ROLE', '') }}"
      user: "{{ env_var('SNOWFLAKE_USER', '') }}"
      authenticator: snowflake_jwt
      private_key_passphrase: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PASSPHRASE', '') }}"
      private_key_path: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PATH', '') }}"

model_defaults:
  dialect: snowflake
```

Generate the key pair once per developer machine. Register its public key on your Snowflake user. Keep the `.p8` file local and out of version control.

```bash
openssl genrsa -out snowflake_key.pem 2048
openssl pkcs8 -topk8 -inform PEM -outform PEM \
  -in snowflake_key.pem -out snowflake_key.p8 \
  -v2 aes256cbc -passphrase pass:<YOUR_PASSPHRASE>
```

```sql
ALTER USER <your_user> SET RSA_PUBLIC_KEY = '<contents_of_snowflake_key.pem>';
```
{% endtab %}

{% tab title="Username & password" %}
```yaml
gateways:
  default:
    connection:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT', '') }}"
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', '') }}"
      database: "{{ env_var('SNOWFLAKE_DATABASE', '') }}"
      role: "{{ env_var('SNOWFLAKE_ROLE', '') }}"
      user: "{{ env_var('SNOWFLAKE_USER', '') }}"
      password: "{{ env_var('SNOWFLAKE_PASSWORD', '') }}"
model_defaults:
  dialect: snowflake
```
{% endtab %}

{% tab title="OAuth" %}
```yaml
gateways:
  default:
    snowflake:
      connection:
        type: snowflake
        account: "{{ env_var('SNOWFLAKE_ACCOUNT', '') }}"
        user: "{{ env_var('SNOWFLAKE_USER', '') }}"
        warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', '') }}"
        database: "{{ env_var('SNOWFLAKE_DATABASE', '') }}"
        role: "{{ env_var('SNOWFLAKE_ROLE', '') }}"
        authenticator: oauth
        token: "{{ env_var('SNOWFLAKE_TOKEN', '') }}"
model_defaults:
  dialect: snowflake
```
{% endtab %}

{% tab title="External browser" %}
```yaml
gateways:
  default:
    snowflake:
      connection:
        type: snowflake
        account: "{{ env_var('SNOWFLAKE_ACCOUNT', '') }}"
        warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', '') }}"
        database: "{{ env_var('SNOWFLAKE_DATABASE', '') }}"
        role: "{{ env_var('SNOWFLAKE_ROLE', '') }}"
        authenticator: externalbrowser
model_defaults:
  dialect: snowflake
```
{% endtab %}
{% endtabs %}

{% hint style="danger" %}
OAuth and external-browser SSO are not recommended for production gateway connections. Use key-pair JWT for service accounts.
{% endhint %}

### Use a DataOS Depot

DataOS Depot is recommended for production. Configure a gateway with `type: depot` and `address: dataos://<depot-name>`. The depot manages the Snowflake credential and access purpose.

Production has no local Docker setup. Apply resources in this order:

```
Snowflake key-pair Secret → Snowflake Depot → Git Secret → Vulcan config.yaml → Vulcan resource
```

| Manifest                        | Purpose                                                   |
| ------------------------------- | --------------------------------------------------------- |
| `secret-snowflake-keypair.yaml` | Stores the Snowflake user, encrypted PEM, and passphrase. |
| `depot-snowflake.yaml`          | Registers URL, database, warehouse, account, and role.    |
| `secret-git-sync.yaml`          | Stores git-sync credentials.                              |
| `config.yaml`                   | Points the gateway at the depot.                          |
| `domain-resource.yaml`          | Defines the workflow and API.                             |

Bind the correct purpose to each secret. A `query` credential cannot create tables. Do not give consumers an `rw` credential.

| Purpose | Who uses it            | What it allows                                     |
| ------- | ---------------------- | -------------------------------------------------- |
| `rw`    | Vulcan workflow        | Reads sources, writes models, and manages schemas. |
| `scan`  | Metadata scanner       | Reads metadata for the catalog and lineage.        |
| `query` | Consumer direct access | Reads Data Product tables.                         |

{% hint style="warning" %}
A misspelled Depot name passes `apply` but fails workflow runs. Ensure `dataos://<depot-name>?purpose=rw` exactly matches the depot manifest name.
{% endhint %}

#### Example gateway configuration

```yaml
gateways:
  default:
    connection:
      type: depot
      address: dataos://snowflakedepot?purpose=rw
```

### Configuration properties

Set these under `gateways.<name>.connection` in `config.yaml`.

| Option                   | Description                             | Required    |
| ------------------------ | --------------------------------------- | ----------- |
| `type`                   | Engine type. Must be `snowflake`.       | Yes         |
| `account`                | Snowflake `<org>-<account>` identifier. | Yes         |
| `user`                   | Connecting username.                    | Yes         |
| `password`               | Password authentication.                | Conditional |
| `warehouse`              | Compute warehouse.                      | Yes         |
| `database`               | Target database.                        | Yes         |
| `role`                   | Authentication role.                    | No          |
| `authenticator`          | Authentication method.                  | No          |
| `token`                  | OAuth 2.0 token.                        | No          |
| `private_key_path`       | Key-pair private-key path.              | No          |
| `private_key_passphrase` | Private-key passphrase.                 | No          |

{% hint style="warning" %}
Use the `<org>-<account>` account format. Inject credentials with environment variables.
{% endhint %}

### Validate the connection

```bash
vulcan migrate        # initializes Vulcan state in Snowflake
vulcan plan           # dry run against your target DB; should succeed with no errors
```

### Next step

Continue to [materialization-behavior.md](materialization-behavior.md "mention") to choose the model kind.
