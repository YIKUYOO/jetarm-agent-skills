#!/usr/bin/env bash
# Install only this project's archived CLI. No third-party clone or package install.
set -euo pipefail
ROOT="${JETARM_AGENT_ROOT:-$HOME/.jetarm_agent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -e "$ROOT/bin/jetarm-full-control-agent" ] || [ -e "$ROOT/env.sh" ]; then
  echo "Existing installation detected. Set JETARM_AGENT_ROOT to a new directory." >&2
  exit 2
fi
mkdir -p "$ROOT/bin" "$ROOT/logs" "$ROOT/skills/active" "$ROOT/skills/quarantine" "$ROOT/skills/disabled"
cp "$SCRIPT_DIR/jetarm_full_control_agent.py" "$ROOT/bin/jetarm-full-control-agent"
chmod +x "$ROOT/bin/jetarm-full-control-agent"
cp -R "$SCRIPT_DIR/skills/." "$ROOT/skills/active/"
cat > "$ROOT/env.sh" <<'EOF'
export JETARM_AGENT_ROOT="${JETARM_AGENT_ROOT:-$HOME/.jetarm_agent}"
export JETARM_AGENT_MODE="full-control"
export JETARM_AGENT_TRANSCRIPT="${JETARM_AGENT_TRANSCRIPT:-$JETARM_AGENT_ROOT/logs/full-control-transcript.jsonl}"
export JETARM_SKILL_ROOT="${JETARM_SKILL_ROOT:-$JETARM_AGENT_ROOT/skills}"
export JETARM_LLM_MODEL="${JETARM_LLM_MODEL:-gpt-5.5}"
export JETARM_LLM_BASE_URL="${JETARM_LLM_BASE_URL:-}"
[ ! -f "$JETARM_AGENT_ROOT/secrets.env" ] || . "$JETARM_AGENT_ROOT/secrets.env"
export PATH="$JETARM_AGENT_ROOT/bin:$PATH"
export ROS_HOSTNAME="${ROS_HOSTNAME:-localhost}"
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
EOF
cat > "$ROOT/bin/jetarm-agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="${JETARM_AGENT_ROOT:-$HOME/.jetarm_agent}"
. "$ROOT/env.sh"
exec "$ROOT/bin/jetarm-full-control-agent" "$@"
EOF
chmod +x "$ROOT/bin/jetarm-agent"
printf 'Installed archive at %s. Source its env.sh before use.
' "$ROOT"
