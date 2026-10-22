---
description: >-
  Configure Vulcan notification targets and event types: Teams webhook,
  Slack webhook and API, and email/SMTP, plus per-user targets.
---

# Notifications

Vulcan can send notifications when certain events occur. Configure notifications and specify recipients in your configuration file.

## Notification targets

Configure notifications with notification targets. Specify targets in a project's [configuration](../README.md) file (`config.yaml`). You can specify multiple targets for a project.

A project can specify both global and user-specific notifications. Each target's notifications are sent for all instances of each [event type](notifications.md#vulcan-event-types) (for example, notifications for `run` are sent for all of the project's environments), except when an [override is configured for development](notifications.md#notifications-during-development).

There are four built-in notification target types: [Teams webhook](notifications.md#teams-webhook-notifications), the two [Slack notification methods](notifications.md#slack-notifications), and [email notification](notifications.md#email-notifications). Specify them in either a specific user's `notification_targets` key or the top-level `notification_targets` configuration key.

This example shows the location of both user-specific and global notification targets:

```yaml
# User notification targets
users:
  - username: User1
    ...
    notification_targets:
      - notification_target_1
        ...
      - notification_target_2
        ...
  - username: User2
    ...
    notification_targets:
      - notification_target_1
        ...
      - notification_target_2
        ...

# Global notification targets
notification_targets:
  - notification_target_1
    ...
  - notification_target_2
    ...
```

### Notifications during development

Events triggering notifications execute repeatedly during code development. To prevent excessive notifications, Vulcan can stop all but one user's notification targets.

Specify the top-level `username` configuration key with a value also present in a user-specific notification target's `username` key to only notify that user. Specify this key in either the project configuration file or a machine-specific configuration file located in `~/.vulcan`. The latter is useful if you always use a specific machine for development.

This example stops all notifications other than those for `User1`:

```yaml
# Top-level `username` key: only notify User1
username: User1
# User1 notification targets
users:
  - username: User1
    ...
    notification_targets:
      - notification_target_1
        ...
      - notification_target_2
        ...
```

## Vulcan event types

Events trigger Vulcan notifications. Specify which events should trigger a notification in the notification target's `notify_on` field.

Vulcan supports notifications for [`plan` application](../concepts/run-and-plan/plan-guide.md) start/end/failure, [`run`](../cli.md#run) start/end/failure, and data quality start/end events.

For `plan` and `run` start/end, the notification message includes the target environment name. For failures, it includes the Python exception or error text.

This table lists each event, its associated `notify_on` value, and its notification message:

| Event                    | `notify_on` key value | Notification message                                            |
| ------------------------ | --------------------- | --------------------------------------------------------------- |
| Plan application start   | apply\_start          | "Plan apply started for environment `{environment}`."           |
| Plan application end     | apply\_end            | "Plan apply finished for environment `{environment}`."          |
| Plan application failure | apply\_failure        | "Failed to apply plan.\n{exception}"                            |
| Vulcan run start         | run\_start            | "Vulcan run started for environment `{environment}`."           |
| Vulcan run end           | run\_end              | "Vulcan run finished for environment `{environment}`."          |
| Vulcan run failure       | run\_failure          | "Failed to run Vulcan.\n{exception}"                            |
| Data quality start       | dq\_start             | "Data quality checks started for environment `{environment}`."  |
| Data quality end         | dq\_end               | "Data quality checks finished for environment `{environment}`." |

You can specify any combination of these events in a notification target's `notify_on` field.

{% hint style="info" %}
**Data quality event names**

Use `dq_start`, `dq_end`, and `dq_failure` for data quality notifications. Migrate older `check_start`, `check_end`, and `check_failure` values to the `dq_*` event names.
{% endhint %}

## Teams webhook notifications

Teams webhook is a first-class notification target. Source the webhook URL from an environment variable so the value does not live in source control:

```bash
export TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/...
```

```yaml
notification_targets:
  - type: teams_webhook
    url: "{{ env_var('TEAMS_WEBHOOK_URL') }}"
    notify_on:
      - apply_failure
      - run_failure
```

You can also configure the URL directly when appropriate:

```yaml
notification_targets:
  - type: teams_webhook
    url: "https://your-org.webhook.office.com/..."
    notify_on:
      - apply_failure
      - run_failure
```

## Slack notifications

Vulcan supports two types of Slack notifications. Slack webhooks notify a Slack channel, but they cannot message specific users. The Slack Web API can notify channels or users.

### Webhook configuration

Vulcan uses Slack's "Incoming Webhooks" for webhook notifications. When you [create an incoming webhook](https://api.slack.com/messaging/webhooks) in Slack, you receive a unique URL associated with a specific Slack channel. Vulcan transmits the notification message by submitting a JSON payload to that URL.

This example shows a Slack webhook notification target. Plan application start, plan application failure, or Vulcan run start trigger notifications. The specification uses an environment variable `SLACK_WEBHOOK_URL` instead of hard-coding the URL:

```yaml
notification_targets:
  - type: slack_webhook
    notify_on:
      - apply_start

      - apply_failure

      - run_start
    url: "{{ env_var('SLACK_WEBHOOK_URL') }}"
```

### API configuration

To notify users, use the Slack API notification target. This requires a Slack API token, which you can use for multiple notification targets with different channels or users. See [Slack's official documentation](https://api.slack.com/tutorials/tracks/getting-a-token) for information on getting an API token.

This example shows a Slack API notification target. Plan application start or plan application end trigger notifications. The specification uses an environment variable `SLACK_API_TOKEN` instead of hard-coding the token:

```yaml
notification_targets:
  - type: slack_api
    notify_on:
      - apply_start

      - apply_end
    token: "{{ env_var('SLACK_API_TOKEN') }}"
    channel: "UXXXXXXXXX"  # Channel or a user's Slack member ID
```

## Email notifications

Vulcan supports notifications via email. The notification target specifies the SMTP host, user, password, and sender address. A target can notify multiple recipient email addresses.

This example shows an email notification target, where `sushi@example.com` emails `data-team@example.com` on Vulcan run failure. The specification uses environment variables `SMTP_HOST`, `SMTP_USER`, and `SMTP_PASSWORD` instead of hard-coding the values:

```yaml
notification_targets:
  - type: smtp
    notify_on:
      - run_failure
    host: "{{ env_var('SMTP_HOST') }}"
    user: "{{ env_var('SMTP_USER') }}"
    password: "{{ env_var('SMTP_PASSWORD') }}"
    sender: sushi@example.com
    recipients:
      - data-team@example.com
```
