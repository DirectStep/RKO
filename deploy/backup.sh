#!/bin/sh
set -eu
umask 077
cd /opt/rko
backup_dir=/var/backups/rko
mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="$backup_dir/rko-$stamp.dump"
temporary="$destination.partial"
trap 'rm -f "$temporary"' EXIT HUP INT TERM
docker compose -f compose.yaml -f compose.production.yaml exec -T db \
    pg_dump -U rko -d rko -Fc > "$temporary"
test -s "$temporary"
docker compose -f compose.yaml -f compose.production.yaml exec -T db \
    pg_restore -l < "$temporary" > /dev/null
mv "$temporary" "$destination"
find "$backup_dir" -maxdepth 1 -type f -name 'rko-*.dump' -mtime +7 -delete
printf '%s\n' "$destination"
