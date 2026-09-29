#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

runtime_dir=.runtime
runtime_file="$runtime_dir/active-backend.conf"
previous_file="$runtime_dir/previous-backend"
migration=false

if (($# > 1)) || { (($# == 1)) && [[ $1 != --migrate-from-legacy ]]; }; then
    printf 'Usage: %s [--migrate-from-legacy]\n' "$0" >&2
    exit 64
fi

if (($# == 1)); then
    migration=true
fi

write_active_backend() {
    local backend=$1 draining=${2:-none} expires temporary
    case "$draining" in
        blue|green|legacy)
            expires=$(date -u -d '+12 hours' '+%a, %d %b %Y %H:%M:%S GMT')
            ;;
        none)
            expires='Thu, 01 Jan 1970 00:00:00 GMT'
            ;;
        *)
            printf 'Unsupported draining backend: %s\n' "$draining" >&2
            exit 65
            ;;
    esac

    temporary=$(mktemp "$runtime_dir/.active-backend.XXXXXX")
    cat >"$temporary" <<EOF
map "" \$active_backend {
    default $backend;
}

map "" \$draining_backend {
    default $draining;
}

map "" \$draining_cookie_expires {
    default "$expires";
}
EOF
    mv "$temporary" "$runtime_file"
}

read_active_backend() {
    local active
    active=$(awk '$1 == "default" { sub(";", "", $2); print $2; exit }' "$runtime_file")
    case "$active" in
        blue|green|legacy) printf '%s\n' "$active" ;;
        *)
            printf 'Invalid active backend file: %s\n' "$runtime_file" >&2
            exit 65
            ;;
    esac
}

wait_for_healthy() {
    local service=$1 container state attempt
    container=$(docker compose ps -q "$service")
    if [[ -z $container ]]; then
        printf 'Container for %s was not created.\n' "$service" >&2
        exit 1
    fi

    for attempt in $(seq 1 80); do
        state=$(docker inspect --format '{{.State.Health.Status}}' "$container")
        case "$state" in
            healthy) return 0 ;;
            unhealthy)
                docker compose logs --tail=200 "$service" >&2
                printf '%s became unhealthy. Active backend was not changed.\n' "$service" >&2
                exit 1
                ;;
        esac
        sleep 5
    done

    docker compose logs --tail=200 "$service" >&2
    printf 'Timed out waiting for %s health check. Active backend was not changed.\n' "$service" >&2
    exit 1
}

mkdir -p "$runtime_dir"

if $migration; then
    if [[ -e $runtime_file ]]; then
        printf 'The runtime backend file already exists; legacy migration is only for the first transition.\n' >&2
        exit 65
    fi

    printf 'Preparing the one-time legacy migration. Nginx will be recreated once; existing WebSockets reconnect to legacy.\n' >&2
    write_active_backend legacy
    docker compose up -d --no-deps nginx
    docker compose exec -T nginx nginx -t
    docker compose exec -T nginx wget -q -T 10 -O /dev/null http://app:8080/
else
    if [[ ! -e $runtime_file ]]; then
        printf 'Missing %s. Copy nginx.active-backend.conf.example before the first HTTPS startup.\n' "$runtime_file" >&2
        exit 65
    fi
    docker compose exec -T nginx nginx -t
fi

active=$(read_active_backend)
case "$active" in
    blue) candidate=green ;;
    green) candidate=blue ;;
    legacy) candidate=blue ;;
    *)
        printf 'Unsupported active backend: %s\n' "$active" >&2
        exit 65
        ;;
esac

printf 'Building image and starting app-%s while %s remains active.\n' "$candidate" "$active"
docker compose build app-blue
docker compose up -d --no-deps "app-$candidate"
wait_for_healthy "app-$candidate"
docker compose exec -T nginx wget -q -T 10 -O /dev/null "http://app-$candidate:8080/"

runtime_backup=$(mktemp "$runtime_dir/.active-backend.previous.XXXXXX")
cp "$runtime_file" "$runtime_backup"
write_active_backend "$candidate" "$active"
if ! docker compose exec -T nginx nginx -t; then
    mv "$runtime_backup" "$runtime_file"
    printf 'Nginx rejected the new runtime configuration. Active backend was restored.\n' >&2
    exit 1
fi

if ! docker compose exec -T nginx nginx -s reload; then
    mv "$runtime_backup" "$runtime_file"
    docker compose exec -T nginx nginx -s reload || true
    printf 'Nginx reload failed. Active backend was restored.\n' >&2
    exit 1
fi
if ! docker compose exec -T nginx wget -q --no-check-certificate \
    --header='Host: dostavo.online' \
    --header="Cookie: dostavo_backend=$candidate" \
    -T 10 -O /dev/null https://127.0.0.1/; then
    mv "$runtime_backup" "$runtime_file"
    if ! docker compose exec -T nginx nginx -s reload; then
        printf 'The backend route check failed and Nginx could not reload the restored configuration. Reload it manually.\n' >&2
    fi
    printf 'Nginx could not route to app-%s. Active backend was restored.\n' "$candidate" >&2
    exit 1
fi
rm -f "$runtime_backup"
printf '%s %s\n' "$active" "$(date -u +%s)" >"$previous_file"

docker compose up -d --no-deps mail-worker
printf 'New visitors now use app-%s. Keep %s running until at least %s UTC.\n' \
    "$candidate" "$active" "$(date -u -d '+12 hours' '+%Y-%m-%dT%H:%M:%SZ')"
