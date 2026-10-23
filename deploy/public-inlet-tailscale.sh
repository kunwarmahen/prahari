#!/usr/bin/env bash
# The inlet on the internet, without a domain or an open router port:
# Tailscale Funnel. Tailscale gives this computer a name
# (https://<computer>.<your-tailnet>.ts.net), holds its certificate, and
# forwards that name's HTTPS to Prahari's inlet-only listener on 127.0.0.1
# -- the inlet ALONE: no page, no API, only POST /inlet/WORD with a key.
# Run it yourself: it signs in to your Tailscale account and asks for your
# password (sudo).
#
#   deploy/public-inlet-tailscale.sh [PORT]
#
# PORT is the inlet-only listener's (prahari serve --inlet-port 8783, or
# [prahari] inlet_port in sarathi.toml). The public name is served on 8443,
# so a Setu catalog on 443 keeps its own. Undo with:
#   sudo tailscale funnel --https=8443 off
set -euo pipefail
PORT="${1:-8783}"

said=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$PORT/inlet/check" || true)
if [ "$said" != "401" ]; then
    echo "Prahari's inlet isn't answering on 127.0.0.1:$PORT (got '$said', want 401)."
    echo "Start it with the inlet alone on that port: prahari serve --inlet-port $PORT"
    echo "(with Sarathi: inlet_port = $PORT under [prahari], then sarathi up)"
    exit 1
fi

if ! command -v tailscale >/dev/null; then
    echo "Installing Tailscale with its own installer (tailscale.com/install.sh)..."
    curl -fsSL https://tailscale.com/install.sh | sh
fi

# Signs this computer in to your tailnet; prints a link to open the first time.
sudo tailscale up

# If Funnel isn't allowed for this computer yet, tailscale prints a link to
# allow it in your tailnet's settings: open it, allow, and run this again.
sudo tailscale funnel --bg --https=8443 "http://127.0.0.1:$PORT"

NAME=$(tailscale status --json | python3 -c \
    'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
PUBLIC="https://$NAME:8443"
echo
echo "The inlet's public address: $PUBLIC/inlet/WORD"
echo -n "It answers a knock with no key: "
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$PUBLIC/inlet/check" || true
echo "(401 is right: it hears only a knock with an inlet key)"
echo
echo "Next, tell Prahari its public address, so its page and your agent show it:"
echo "  prahari serve --inlet-port $PORT --inlet-public-url $PUBLIC"
echo "  (with Sarathi: public_url = \"$PUBLIC\" under [prahari], then sarathi up)"
