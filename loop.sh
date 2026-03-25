#!/bin/bash
#
# Ralph Loop - runs Claude CLI repeatedly in headless mode.
#
# Each iteration, Claude reads a prompt file that tells it to:
#   - plan mode: analyze specs/code and update IMPLEMENTATION_PLAN.md
#   - build mode: pick the top task from the plan, implement it, test it
#
# IMPLEMENTATION_PLAN.md is the shared state between iterations.
# Claude reads it at the start of each loop to know what's done and what's next.
#
# Usage:
#   ./loop.sh              # build mode, runs until you Ctrl+C
#   ./loop.sh plan         # plan mode, runs until you Ctrl+C
#   ./loop.sh build 10     # build mode, stops after 10 iterations
#   ./loop.sh plan 5       # plan mode, stops after 5 iterations
#   ./loop.sh 10           # shorthand: build mode, 10 iterations
#
# Prerequisites:
#   - Claude CLI installed (npm install -g @anthropic-ai/claude-code)
#   - Git repo initialized in your project
#   - PROMPT_plan.md and/or PROMPT_build.md in project root

# --- Parse arguments ---

# First arg: mode ("plan" or "build") or a number (treated as max iterations for build)
# Second arg: max iterations (optional)

if [ "$1" = "plan" ]; then
    MODE="plan"
    MAX=${2:-0}
elif [ "$1" = "build" ]; then
    MODE="build"
    MAX=${2:-0}
elif [[ "$1" =~ ^[0-9]+$ ]]; then
    MODE="build"
    MAX=$1
else
    MODE="build"
    MAX=0
fi

PROMPT="PROMPT_${MODE}.md"
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
COUNT=0

# --- Preflight checks ---

if [ ! -f "$PROMPT" ]; then
    echo "Error: $PROMPT not found in $(pwd)"
    echo "Copy the prompt templates into your project root first."
    exit 1
fi

# --- Print config ---

echo "----------------------------------------"
echo "  Ralph Loop"
echo "  Mode:   $MODE"
echo "  Prompt: $PROMPT"
echo "  Branch: $BRANCH"
[ "$MAX" -gt 0 ] && echo "  Max:    $MAX iterations"
echo "  Stop:   Ctrl+C"
echo "----------------------------------------"
echo ""

# --- Main loop ---

while true; do
    # Check iteration limit
    if [ "$MAX" -gt 0 ] && [ "$COUNT" -ge "$MAX" ]; then
        echo "Done. Reached max iterations ($MAX)."
        break
    fi

    COUNT=$((COUNT + 1))
    echo "=== Iteration $COUNT ==="

    # Run Claude in headless mode.
    #
    # Flags explained:
    #   -p                              Read prompt from stdin (non-interactive / headless)
    #   --dangerously-skip-permissions  Let Claude run tools without asking (careful with this)
    #   --model opus                    Use Opus for reasoning quality; change to "sonnet" for speed
    #   --verbose                       Show detailed execution info
    #
    # The prompt file is piped in via stdin. Claude reads it, then reads your project
    # files (specs, code, IMPLEMENTATION_PLAN.md) as instructed by the prompt.
    cat "$PROMPT" | claude -p \
        --dangerously-skip-permissions \
        --model opus \
        --verbose

    # Push changes after each iteration (Claude commits inside the prompt instructions)
    git push origin "$BRANCH" 2>/dev/null || git push -u origin "$BRANCH" 2>/dev/null

    echo ""
done
