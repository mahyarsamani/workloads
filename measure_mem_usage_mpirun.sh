#!/usr/bin/env bash
#
# Usage: run_branson_mem.sh mpirun [args...]
#
# Example:
#   ./run_branson_mem.sh mpirun -n 4 ./BRANSON input.xml
#
# This script will:
#   1) Launch your MPI command (including mpirun) in the background, storing the outer PID in OUTER_PID.
#   2) Sleep a bit, then check if OUTER_PID is actually mpirun or a short-lived wrapper.
#   3) If it's not mpirun, search its child processes to find the real mpirun PID.
#   4) Once we have mpirun's PID (MPIRUN_PID), we poll ps --ppid MPIRUN_PID
#      for direct children, sum their RSS, and print once per second.
#   5) Stop when mpirun exits.

if [ $# -lt 1 ]; then
  echo "Usage: $0 mpirun [args...]"
  echo "Example: $0 mpirun -n 4 ./BRANSON input.xml"
  exit 1
fi

################################################################################
# Helper: Recursively search for a process named 'mpirun' or 'mpiexec'
# under a given PID (checking that PID and all descendants).
################################################################################
find_mpirun_pid() {
  local parent_pid="$1"

  # If parent_pid is alive, check if it's mpirun/mpiexec
  if kill -0 "$parent_pid" 2>/dev/null; then
    local comm
    comm=$(ps -o comm= -p "$parent_pid" 2>/dev/null)
    if [ "$comm" = "mpirun" ] || [ "$comm" = "mpiexec" ]; then
      echo "$parent_pid"
      return 0
    fi
  fi

  # Otherwise, look among direct children
  local child
  for child in $(pgrep -P "$parent_pid"); do
    local found
    found=$(find_mpirun_pid "$child")
    if [ -n "$found" ]; then
      echo "$found"
      return 0
    fi
  done

  return 1
}

# Combine entire command
cmd="$*"
echo "[INFO] Launching in background: $cmd"

# 1) Launch the MPI command in background
$cmd &
OUTER_PID=$!

echo "[INFO] Outer PID: $OUTER_PID"

sleep 5

# Check if OUTER_PID is still alive
if ! kill -0 "$OUTER_PID" 2>/dev/null; then
  echo "[WARN] Outer PID ($OUTER_PID) exited quickly."
  # Possibly ephemeral. We'll try to find mpirun among its children (if any).
  MPIRUN_PID=$(find_mpirun_pid "$OUTER_PID")
else
  # OUTER_PID is alive, so see if it's actually mpirun
  comm=$(ps -o comm= -p "$OUTER_PID" 2>/dev/null)
  if [ "$comm" = "mpirun" ] || [ "$comm" = "mpiexec" ]; then
    # Great, OUTER_PID is truly mpirun
    MPIRUN_PID=$OUTER_PID
  else
    # It's something else, so we search its children
    MPIRUN_PID=$(find_mpirun_pid "$OUTER_PID")
  fi
fi

# If we still didn't find mpirun, bail out
if [ -z "$MPIRUN_PID" ]; then
  echo "[ERROR] Could not find a running mpirun/mpiexec process."
  exit 1
fi

echo "[INFO] Found mpirun PID: $MPIRUN_PID"

# If mpirun isn't alive at this point, we won't do much
if ! kill -0 "$MPIRUN_PID" 2>/dev/null; then
  echo "[WARN] mpirun (PID $MPIRUN_PID) is not alive. Maybe finished?"
  exit 0
fi

echo "[INFO] Tracking memory usage of mpirun's direct children via ps --ppid..."

# 2) Loop until mpirun is gone
while kill -0 "$MPIRUN_PID" 2>/dev/null; do
  total_rss=0

  # Direct children of mpirun
  child_pids=$(ps --no-headers --ppid "$MPIRUN_PID" -o pid=)

  for pid in $child_pids; do
    mem_kb=$(ps -o rss= -p "$pid" 2>/dev/null)
    if [[ "$mem_kb" =~ ^[0-9]+$ ]]; then
      total_rss=$((total_rss + mem_kb))
    fi
  done

  echo "$(date +%H:%M:%S) - Direct children of PID $MPIRUN_PID => ${total_rss} kB"
  sleep 3
done

echo "[INFO] mpirun (PID $MPIRUN_PID) has finished."
