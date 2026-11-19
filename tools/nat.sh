#!/usr/bin/env bash
# Give the Pi internet through the laptop's hotspot.
#
# NetworkManager's shared mode brings up the hotspot, dnsmasq and DHCP but
# never installs the NAT rules on this machine, so the Pi gets an address and
# no route out. The rules are runtime-only and vanish on reboot, so this has
# to be re-run -- /etc/NetworkManager/dispatcher.d/90-pi-nat does that on
# every interface change.
#
# The uplink is whatever currently owns the default route. That changes
# between phone tethering and wired ethernet, so it is detected rather than
# hardcoded; the old hand-typed version named enxa6c337b9f279 and silently
# stopped working when the uplink moved.
#
# Run as root:  sudo tools/nat.sh

set -euo pipefail

# iptables and sysctl live in /usr/sbin, which is not on a normal user PATH.
export PATH=/usr/sbin:/sbin:$PATH

HOTSPOT_IF=${HOTSPOT_IF:-wlp0s20f3}
SUBNET=${SUBNET:-10.42.0.0/24}

UPLINK_IF=$(ip route show default |
    awk '/^default/ {for (i = 1; i <= NF; i++) if ($i == "dev") {print $(i + 1); exit}}')

if [ -z "$UPLINK_IF" ]; then
    echo "nat: no default route, is the laptop online?" >&2
    exit 1
fi
if [ "$UPLINK_IF" = "$HOTSPOT_IF" ]; then
    echo "nat: default route is the hotspot itself, nothing to share" >&2
    exit 1
fi

echo "nat: sharing $UPLINK_IF -> $HOTSPOT_IF ($SUBNET)"

sysctl -qw net.ipv4.ip_forward=1

# -C tests for an existing rule, so re-running does not stack duplicates.
add() {
    local table=$1
    shift
    if iptables -t "$table" -C "$@" 2>/dev/null; then
        echo "  present: $*"
    else
        iptables -t "$table" -A "$@"
        echo "  added:   $*"
    fi
}

add nat POSTROUTING -s "$SUBNET" ! -d "$SUBNET" -j MASQUERADE
add filter FORWARD -i "$HOTSPOT_IF" -o "$UPLINK_IF" -j ACCEPT
add filter FORWARD -i "$UPLINK_IF" -o "$HOTSPOT_IF" \
    -m state --state RELATED,ESTABLISHED -j ACCEPT
