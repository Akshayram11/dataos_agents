# Data Product Consumption Agent

Private, owner-only agentic application for the Engineering DataOS tenant. The model can access DataOS data only through the fixed Arguss Data Product MCP endpoint.

## Security boundary

- UI and APIs are restricted to `akshaychametmdcio`.
- The user supplies their own DataOS API key and OpenAI API key.
- Both keys are validated and AES-256-GCM encrypted on the Service's private stateful disk.
- Keys are never returned to the browser, written into manifests, or logged.
- The application identity has only the compute permissions required to run the Service.
- The agent pins nine read-only, non-destructive MCP tools. It has no `dataos-ctl`, Poros, Git, shell, web-search, or arbitrary MCP access.
- Data returned by MCP for a question is sent to OpenAI to generate the answer.

## Local verification

```sh
node --test runtime/server.test.mjs
python3 -m unittest discover -s tests -v
```

## Deploy

```sh
python3 install.py environment.json \
  --cli /Users/akshaychame/.dataos/v2/bin/dataos-ctl \
  --apply
```
