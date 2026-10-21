#!/bin/bash
# Run once, after you have created your own account. Closes sign-ups so no other account can be made.
# (The chat is already only reachable from this computer; this is an extra lock.)
cd "$(dirname "$0")/librechat" || exit 1
perl -pi -e 's/^ALLOW_REGISTRATION=.*/ALLOW_REGISTRATION=false/' .env
docker compose restart api >/dev/null 2>&1 && echo "Sign-ups are closed. Your account still works."
