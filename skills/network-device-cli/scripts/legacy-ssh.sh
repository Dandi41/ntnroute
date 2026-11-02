#!/usr/bin/env bash
# Run one command on a legacy-SSH network device (Cisco IOS et al) without
# sshpass/expect and without root.
#
#   PW=... ./legacy-ssh.sh <host> <user> [command]
#
# Prints device output with CRs stripped. Exit code mirrors ssh.
set -uo pipefail

HOST=${1:?usage: legacy-ssh.sh <host> <user> [command]}
USERNAME=${2:?usage: legacy-ssh.sh <host> <user> [command]}
CMD=${3:-}

if [ -z "${PW:-}" ]; then
  read -rsp "password for ${USERNAME}@${HOST}: " PW; echo
fi

ASKPASS=$(mktemp /tmp/askpass.XXXXXX.sh)
# The password is read by the helper from the environment, never written to disk
# and never on ssh's argv (visible in ps).
printf '#!/bin/bash\nprintf "%%s\\n" "$PW_HOLDER"\n' > "$ASKPASS"
chmod 700 "$ASKPASS"
trap 'rm -f "$ASKPASS"' EXIT

# Hold the channel open: with </dev/null IOS closes the session the instant auth
# succeeds and the reply arrives truncated.
{ sleep 25; } | PW_HOLDER="$PW" SSH_ASKPASS="$ASKPASS" SSH_ASKPASS_REQUIRE=force DISPLAY=:0 \
  ssh -tt \
    -o ConnectTimeout=20 \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1,diffie-hellman-group-exchange-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedAlgorithms=+ssh-rsa \
    -o Ciphers=+aes128-cbc,3des-cbc \
    -o MACs=+hmac-sha1 \
    -o PreferredAuthentications=password \
    -o NumberOfPasswordPrompts=1 \
    "${USERNAME}@${HOST}" ${CMD:+"$CMD"} 2>&1 | tr -d '\r'
