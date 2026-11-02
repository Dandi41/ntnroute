#!/usr/bin/env bash
# ios_session.sh — persistent PTY session against a network device CLI (Cisco IOS shape).
# OpenSSH re-implementation of ios_session.py: same CLI, same output shape, no Python,
# no paramiko — it uses the engine's own technique (ssh -tt + SSH_ASKPASS + a paced
# command plan of `delay<TAB>line` pairs typed into the PTY).
#
#   ios_session.sh --host 10.0.0.1 --user admin --password 'pw' \
#       [--port 22] [--secret ENABLE] --cmd 'show version' --cmd 'show ip int brief'
#   ios_session.sh ... --show-config              # full running-config
#   ios_session.sh ... --paging ''                # disable the terminal length 0 preset
#
# Reports the prompt it actually saw, so an enable failure is visible instead of
# silent. Exit 2 on connect failure, 0 otherwise.
#
# Differences from the paramiko version, on purpose:
#   - pacing is a fixed plan (the engine's approach), not read-until-idle
#   - --paging '' means no terminal length 0 is sent; --More-- is then NOT
#     auto-answered (keep the default paging for long output)
#   - --secret sends `enable` + the secret unconditionally; if the session was
#     already privileged the secret lands at the prompt and errors harmlessly
set -o pipefail

usage() {
  echo "usage: ios_session.sh --host H [--port P] --user U --password PW [--secret S]" >&2
  echo "                      [--cmd CMD]... [--show-config] [--paging 'terminal length 0']" >&2
  exit 2
}

host="" port=22 user="" password="" secret="" paging="terminal length 0" show_config=0
cmds=()
while [ $# -gt 0 ]; do
  case "$1" in
    --host) [ $# -ge 2 ] || usage; host=$2; shift 2;;
    --port) [ $# -ge 2 ] || usage; port=$2; shift 2;;
    --user) [ $# -ge 2 ] || usage; user=$2; shift 2;;
    --password) [ $# -ge 2 ] || usage; password=$2; shift 2;;
    --secret) [ $# -ge 2 ] || usage; secret=$2; shift 2;;
    --cmd) [ $# -ge 2 ] || usage; cmds+=("$2"); shift 2;;
    --show-config) show_config=1; shift;;
    --paging) [ $# -ge 2 ] || usage; paging=$2; shift 2;;
    -h|--help|--*) usage;;
    *) usage;;
  esac
done
[ -n "$host" ] && [ -n "$user" ] && [ -n "$password" ] || usage

T=$(mktemp -d) || exit 2
trap 'rm -rf "$T"' EXIT

# askpass supplies the SSH login password only (the enable secret, if any, is a
# paced plan line typed into the PTY like keyboard input)
printf '#!/bin/sh\necho "$IOS_SESSION_PASSWORD"\n' > "$T/askpass"
chmod 700 "$T/askpass"

# paced plan: delay<TAB>line
{
  printf '4\t\n'                                   # settle banner, capture first prompt
  if [ -n "$secret" ]; then
    printf '2\tenable\n'
    printf '2\t%s\n' "$secret"
  fi
  [ -n "$paging" ] && printf '2\t%s\n' "$paging"
  for c in "${cmds[@]}"; do printf '3\t%s\n' "$c"; done
  [ "$show_config" = 1 ] && printf '10\tshow running-config\n'
  printf '2\texit\n1\texit\n'
} > "$T/plan"

# feeder paces the plan via process substitution; if ssh closes early the
# feeder's SIGPIPE is harmless — the session's exit code comes from ssh itself
IOS_SESSION_PASSWORD="$password" SSH_ASKPASS="$T/askpass" \
    SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-:0}" setsid \
    ssh -tt -p "$port" \
      -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o KexAlgorithms=+diffie-hellman-group14-sha1 \
      -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa \
      -o Ciphers=+aes128-cbc -o MACs=+hmac-sha1 \
      -o ConnectTimeout=20 \
      "$user@$host" < <(
        while IFS=$'\t' read -r d line; do
          sleep "$d"
          [ -n "$line" ] && printf '%s\n' "$line"
        done < "$T/plan"
      ) > "$T/raw" 2> "$T/ssherr"
rc=$?
if [ $rc -ne 0 ]; then
  msg=$(grep -v '^Warning:' "$T/ssherr" 2>/dev/null | head -n 1)
  echo "connect failed: ssh exit ${rc}${msg:+: $msg}" >&2
  exit 2
fi

# strip ANSI + CR, then reconstruct the Python-shaped report from the transcript
sed -e 's/\x1b\[[0-9;?]*[A-Za-z]//g' -e 's/\x1b\][^\x07]*\x07//g' -e 's/\r//g' \
    "$T/raw" > "$T/clean"

CMDS="" ; for c in "${cmds[@]}"; do CMDS="${CMDS:+$CMDS
}$c"; done
export IOS_CMDS="$CMDS" IOS_PAGING="$paging" IOS_SECRET="$secret" IOS_SHOWCFG="$show_config"

AWK_BIN=$(command -v gawk || command -v awk)
[ -n "$AWK_BIN" ] || { echo "ios_session: no awk found" >&2; exit 2; }
# the parser needs gawk's 3-argument match(); probe rather than assume
"$AWK_BIN" 'BEGIN { match("ab", /(b)/, m) }' 2>/dev/null || {
  echo "ios_session: this awk lacks 3-argument match() — install gawk" >&2; exit 2
}
LC_ALL=C "$AWK_BIN" '
function strip(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
# On a piped PTY the prompt is never a standalone line: the device prints it
# and the next typed command lands on the same line ("R2>show clock"). So a
# prompt is a line PREFIX like ^hostname[>#], and each echo line both ends the
# previous section and starts the next one.
function prompt_of(s,    m) {
  if (match(s, /^([A-Za-z0-9_.-]{1,63}[>#])/, m)) return m[1]
  return ""
}
# consume: find the echo of `cmd` from pos onward (prompt-prefixed or bare),
# emit (or skip) the section up to the next prompt-bearing line, and return
# the index of that line, so the next section can claim its own echo from it
function consume(pos, cmd, pr,    i, s, started) {
  started = 0
  for (i = pos; i <= NR; i++) {
    s = strip(lines[i])
    if (!started) {
      if (s == cmd || (length(s) > length(cmd) && substr(s, length(s) - length(cmd) + 1) == cmd)) {
        started = 1
        if (pr) printf "\n$ %s\n", cmd
      }
      continue
    }
    if (prompt_of(lines[i]) != "") return i
    if (pr) print lines[i]
  }
  return NR + 1
}
{ lines[NR] = $0 }
END {
  for (i = 1; i <= NR; i++) {
    p = prompt_of(lines[i])
    if (p != "") { if (ip == "") ip = p; fp = p }
  }
  sec = ENVIRON["IOS_SECRET"] != ""
  if (ip ~ /#$/)
    st = "already privileged"
  else if (!sec)
    st = "no secret given; staying in user exec"
  else if (fp ~ /#$/)
    st = "privileged OK"
  else
    st = "enable FAILED (prompt \x27" fp "\x27)"
  print "# " st

  pos = 1
  if (ENVIRON["IOS_PAGING"] != "") pos = consume(pos, ENVIRON["IOS_PAGING"], 0)
  n = split(ENVIRON["IOS_CMDS"], C, "\n")
  for (k = 1; k <= n; k++) if (C[k] != "") pos = consume(pos, C[k], 1)
  if (ENVIRON["IOS_SHOWCFG"] == "1") pos = consume(pos, "show running-config", 1)
  printf "\n# final prompt: \x27%s\x27\n", fp
}
' "$T/clean"
