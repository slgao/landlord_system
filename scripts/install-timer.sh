#!/bin/bash
# Install the nightly backup as a systemd *user* timer, replacing the cron job.
#
# Why user rather than system: the units run as you, so backup.sh finds $HOME,
# writes to ~/landlord_backups, and can reach your desktop session to raise a
# notification when a dump fails. A system unit would run as root and manage
# none of that cleanly.
#
# Requires lingering, so the timer still fires when you are not logged in:
#   loginctl enable-linger "$USER"
#
# Idempotent — safe to re-run after moving the checkout or editing the units.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$UNIT_DIR" "$HOME/landlord_backups"

for unit in landlord-backup.service landlord-backup.timer; do
    sed "s|@PROJECT_DIR@|$PROJECT_DIR|g" "$SCRIPT_DIR/systemd/$unit" > "$UNIT_DIR/$unit"
    echo "installed $UNIT_DIR/$unit"
done

systemctl --user daemon-reload
systemctl --user enable --now landlord-backup.timer

if ! loginctl show-user "$USER" -p Linger --value 2>/dev/null | grep -q yes; then
    echo
    echo "WARNING: lingering is off, so the timer only runs while you are logged in."
    echo "         Enable it with:  loginctl enable-linger $USER"
fi

# The cron entry and the timer would otherwise both fire at 22:00, producing two
# dumps a night and doubling the retention churn.
if crontab -l 2>/dev/null | grep -q 'scripts/backup.sh'; then
    echo
    echo "NOTE: a cron entry for backup.sh is still installed and will now double up."
    echo "      Remove it with:"
    echo "        crontab -l | grep -v 'scripts/backup.sh' | crontab -"
fi

echo
systemctl --user list-timers landlord-backup.timer --no-pager
