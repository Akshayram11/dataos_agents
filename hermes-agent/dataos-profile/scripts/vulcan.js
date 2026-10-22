#!/usr/bin/env node
const { spawnSync } = require("child_process");

const result = spawnSync("/opt/venv/bin/vulcan", process.argv.slice(2), {
  cwd: process.cwd(),
  env: {
    ...process.env,
    LD_LIBRARY_PATH: ["/opt/libs", process.env.LD_LIBRARY_PATH || ""].filter(Boolean).join(":"),
    PYTHONNOUSERSITE: "1",
  },
  stdio: "inherit",
});

if (result.error) {
  console.error(`Vulcan runtime failed to start: ${result.error.message}`);
  process.exitCode = 1;
} else {
  process.exitCode = result.status ?? 1;
}
