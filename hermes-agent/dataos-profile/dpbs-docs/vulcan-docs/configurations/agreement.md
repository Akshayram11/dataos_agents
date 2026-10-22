---
description: >-
  What agreement.md is for, how it differs from config.yaml and
  usage.yaml, and how Vulcan resolves, reads, and surfaces it to
  consumers.
---

# Agreement (agreement.md)

`agreement.md` is an optional, sidecar file for the data-sharing or usage agreement between a data product's producer and its consumers. It's distinct from both `config.yaml` (runtime configuration) and `usage.yaml` (informal usage guidance: good-for/not-for/caveats). `agreement.md` is where a producer puts the agreement itself — the terms a consumer should read, and accept, before they start querying.

Vulcan doesn't parse this file. There's no schema and no keys: whatever is in `agreement.md` is read verbatim and surfaced to consumers as-is, most visibly in the **Accept & Follow** confirmation shown before someone follows a product that has one.

`agreement.md` is referenced from `config.yaml` via the `agreement_path` key (default: `agreement.md`), inline via the `agreement` key, or the `VULCAN__AGREEMENT_PATH` environment variable. See [Configurations](README.md) for how it fits into the overall project layout.

The file is optional. If nothing exists at `agreement_path`, Vulcan logs a warning and continues loading the project rather than failing — the product simply has no agreement text. Consumers then see the product's `GET /api/v1/metadata/agreement` endpoint return `404`, and they can follow the product immediately, with no Accept & Follow step.

## When to create `agreement.md`

Add this file once a data product is governed by terms a consumer needs to see and actively agree to: a data-sharing agreement, usage restrictions, retention commitments, or compliance-driven access conditions. Skip it for ordinary internal products where `usage.yaml` already covers the relevant caveats — `agreement.md` is for wording a consumer has to accept, not general usage guidance.

## What goes in it

Anything you'd want a consumer to read and accept before they get access. There's no required structure or set of fields — write it the way you'd write any agreement document.

For a product with nothing more than a redistribution and retention rule to state, that's a couple of sentences and nothing else. The example below is for a more demanding case: a renewal-risk product that scores accounts for churn and is consumed by both Sales Ops (for dashboards) and Customer Success (for outreach), and that carries customer PII. An agreement for that kind of product typically has to cover several things at once — who's allowed to use it and for what, which specific analyses are in scope, the ways it could be misused (feeding a churn score into a termination decision without a human looking at it first, or into a model, or trying to re-identify anonymized rows), where the data and its extracts are allowed to live, when extracts have to be deleted, how derived reports should credit the source, and what happens if someone breaks the rules. Note this is illustrative only — the sections, the product, and the wording are all made up for the example; write whatever your own product's terms actually are:

```markdown
# Usage Agreement — Renewal Risk Insights

This is the agreement for accessing **Renewal Risk Insights**
(`renewal-risk-insights`). Read it before continuing — accepting it is what
grants access; declining ends the request with nothing provisioned.

## Who this covers

Access is scoped to producing internal insight and decision support, not
to any other use. That covers Sales Ops working from the Tableau dashboard,
Customer Success acting on renewal alerts, and any AI agent running on
behalf of either team.

## What you can use it for

- Flagging accounts at high or medium renewal risk from health-score and
  contract-expiry data.
- Rolling up monthly recurring revenue by segment and region.
- Watching for contracts inside a 90-day expiry window with no renewal
  logged yet.
- Ranking territories by at-risk revenue for planning purposes.

Anything you build from this data — a report, a chart, a summary — stays
inside that same purpose.

## What you can't use it for

- Publishing, exporting, or handing the data (or anything built from it)
  to anyone outside the org.
- Treating it as billing or revenue-recognition data — the numbers here
  are a snapshot for analysis, not a ledger.
- Acting on a risk flag as a final decision — it's a signal to look into,
  not grounds on its own to end an account relationship.
- Feeding it into model training or evaluation without separate sign-off.
- Trying to re-identify any row that's been anonymized.
- Building a profile of an individual contact beyond the stated purpose.
- Reselling or otherwise commercializing it.

## How to handle it

Keep it inside approved tools only — the dashboard, the semantic API, and
any AI-agent client that's been cleared for it. No copies on personal
devices or unmanaged storage.

This product carries customer names, which is PII. When you pull an
extract, take only what the task needs — an account ID instead of a name
wherever a name isn't specifically required.

## How long you can keep it

Delete any extract once the analysis it was for is done, unless there's a
documented reason to keep it longer. The source data stays governed by
whatever retention policy already applies to it.

## Crediting it

If you publish something built from this data, name the source
(**Renewal Risk Insights**) and the refresh date you used. It updates
daily, so don't treat it as a live feed.

## If the rules aren't followed

Access is logged. Anything that looks like a violation gets treated as a
governance issue and can mean losing access, or worse depending on policy.

## How long this applies

This agreement holds for as long as you have access, and for anything you
still hold onto afterward.
```

Whatever you write is what consumers see, unedited — keep it in the form you'd actually want them to read.

## Related pages

* [Configurations overview](README.md)
* [Usage guidance](usage.md)
