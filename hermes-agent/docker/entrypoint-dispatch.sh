#!/bin/sh
# shellcheck shell=sh
# Entry-point dispatcher for runtimes that may or may not give the image
# ownership of PID 1.
#
# Normal Docker / Podman path: this script is PID 1, so we delegate to
# s6-overlay's /init exactly as before and keep the full supervision tree.
#
# Wrapped-runtime path (Fly Machines, `docker run --init`, some Nomad/K8s
# setups): the platform's own init is already PID 1 and execs the image
# entrypoint as a child. s6-overlay aborts there with "can only run as pid 1",
# so we run the stage2 bootstrap directly and then exec the main wrapper
# without /init.

set -e

# DataOS Services deliberately run the workload as a platform-assigned,
# unprivileged UID (currently 1000).  In that environment the process can be
# PID 1 but s6-overlay cannot repair root-owned /run, so selecting /init merely
# from PID ownership crash-loops.  Use the reviewed rootless bootstrap and run
# the only public process (the authenticated dashboard) in the foreground.
if [ "$(id -u)" -ne 0 ]; then
    export HERMES_DATAOS_ROOTLESS=1
    # The DataOS container stack does not deliver custom Service env entries
    # to this container consistently. Its manifest therefore passes the exact
    # owner and an irreversible scrypt hash as argv (never the password).
    # Session signing intentionally uses the provider's random per-process key.
    if [ "${1:-}" = dataos-dashboard ]; then
        export HERMES_DASHBOARD_BASIC_AUTH_USERNAME="${2:-}"
        export HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH="${3:-}"
        unset HERMES_DASHBOARD_BASIC_AUTH_SECRET
        shift 3
    fi
    # The browser tool is disabled in the DataOS profile.  A non-empty value
    # also keeps stage2 from attempting to write s6's root-owned envdir.
    export AGENT_BROWSER_EXECUTABLE_PATH="${AGENT_BROWSER_EXECUTABLE_PATH:-disabled-in-dataos}"
    /opt/hermes/docker/stage2-hook.sh
    export HOME="${HERMES_HOME:-/opt/data}"
    cd "$HOME"
    # Existing stateful profiles may predate the explicit DataOS plugin
    # allow-list. Reconcile this single reviewed provider on every boot; the
    # operation is idempotent and the dashboard still fails closed if its
    # credentials are absent. Report presence only, never credential values.
    for auth_key in \
        HERMES_DASHBOARD_BASIC_AUTH_USERNAME \
        HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH \
        HERMES_DASHBOARD_BASIC_AUTH_SECRET; do
        eval "auth_value=\${$auth_key:-}"
        if [ -n "$auth_value" ]; then
            echo "[dataos] $auth_key=set"
        else
            echo "[dataos] $auth_key=missing" >&2
        fi
    done
    unset auth_value
    hermes plugins enable basic --no-allow-tool-override
    exec hermes dashboard \
        --host "${HERMES_DASHBOARD_HOST:-0.0.0.0}" \
        --port "${HERMES_DASHBOARD_PORT:-9119}" \
        --no-open
fi

if [ "$$" -eq 1 ]; then
    # The interactive CMD owns the terminal. Supervised gateways and dashboard
    # output must go to s6's logger instead of overwriting the TUI or shell.
    # Resolve this before /init wires the service descriptors, leaving headless
    # docker logs and explicit s6 settings unchanged.
    if [ -t 0 ] && [ -t 1 ]; then
        export S6_LOGGING="${S6_LOGGING:-2}"
        export S6_CMD_USE_TERMINAL="${S6_CMD_USE_TERMINAL:-1}"
    fi
    exec /init /opt/hermes/docker/main-wrapper.sh "$@"
fi

echo "[hermes] WARNING: container entrypoint is not PID 1; skipping s6-overlay /init and falling back to direct bootstrap. Supervised services are unavailable in this runtime, but the requested command will still run." >&2
# /init normally seeds PATH with s6's helpers; the non-PID-1 fallback skips it.
export PATH="/command:/package/admin/s6/command:${PATH}"
/opt/hermes/docker/stage2-hook.sh
exec /opt/hermes/docker/main-wrapper.sh "$@"
