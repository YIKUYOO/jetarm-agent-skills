# Project rules

Read README.md before using these experimental robotics helpers. Default to offline preview and observation. Physical motion requires explicit current user authorization, a supervised clear workcell, fresh camera evidence, one control stack, readable servo state and an available stop.

Use `--execute` only after these conditions are established. A command return value or software servo state alone does not prove physical motion. Evaluate object displacement and grasp retention using independent before/after observations. Preserve failure evidence and report unknown outcomes honestly. Do not claim a trained VLA model or statistically verified multi-position success.

Keep credentials, network addresses, raw workcell imagery and local-only logs outside the public repository. Run offline tests after code changes. Hardware acceptance must be recorded separately from offline validation.
