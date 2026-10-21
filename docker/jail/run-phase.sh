#!/bin/sh
set -eu

MANIFEST=/tmp/jail-commands.txt
run_traced() {
  strace -f -e trace=open,openat,execve,connect su -s /bin/sh agent -c "$1" || true
}

if [ ! -f "${MANIFEST}" ]; then
  exec strace -f -e trace=open,openat,execve,connect su -s /bin/sh agent -c true
fi

while IFS= read -r line || [ -n "${line}" ]; do
  [ -z "${line}" ] && continue
  run_traced "${line}"
done < "${MANIFEST}"
