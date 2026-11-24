#!/usr/bin/env bash
# Bang Bang offline — one-click launcher for Linux (Windows: double-click Choi_Ngay.bat).
#
#   ./play.sh              start the server (or reuse a running one) and open the game
#   ./play.sh --shortcut   also add "Bang Bang" to the application menu
#   ./play.sh --no-browser start without opening a browser
#
# Needs only python3 >= 3.12 (standard library, no pip). Ctrl+C stops the server.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"

OPEN_BROWSER=1
for arg in "$@"; do
  case "$arg" in
    --no-browser) OPEN_BROWSER=0 ;;
    --shortcut)
      app_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
      mkdir -p "$app_dir"
      cat > "$app_dir/bangbang-offline.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bang Bang
Comment=Bang Bang offline
Exec="$ROOT/play.sh"
Path=$ROOT
Terminal=true
Categories=Game;
EOF
      echo "Đã thêm 'Bang Bang' vào menu ứng dụng: $app_dir/bangbang-offline.desktop" ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Không hiểu tùy chọn: $arg (xem ./play.sh --help)"; exit 2 ;;
  esac
done

# --- Python ----------------------------------------------------------------
PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
      PY="$candidate"; break
    fi
  done
fi
if [[ -z "$PY" ]]; then
  echo "Cần Python 3.12 trở lên. Ubuntu/Debian: sudo apt install python3"
  exit 1
fi

DB="${BB_DATABASE:-$ROOT/data/bangbang.sqlite3}"
KEY="${BB_ADMIN_KEY:-$ROOT/data/admin_buff.key}"
if [[ ! -f "$DB" ]]; then
  echo "Thiếu database: $DB. Hãy tải đầy đủ thư mục game; không tự tạo file rỗng."
  exit 1
fi

health() { # $1 = port → prints the health JSON if a Bang Bang server answers
  curl -s -m 1 "http://127.0.0.1:$1/health" 2>/dev/null | grep -q '"service": "bangbang-private"'
}
free_port() { # first free local port from $1
  "$PY" - "$1" <<'EOF'
import socket, sys
start = int(sys.argv[1])
for port in range(start, start + 30):
    with socket.socket() as s:
        # Same option the server uses, so a just-stopped server (TIME_WAIT) does not push us to the next port.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            continue
        print(port); break
else:
    sys.exit('Không còn cổng trống quanh ' + str(start))
EOF
}
open_game() {
  local url="http://127.0.0.1:$1/html5/"
  echo "Game:          $url"
  echo "Cẩm nang tank: http://127.0.0.1:$1/tank-guide/"
  echo "Web buff:      http://127.0.0.1:$1/admin/buff/  (khóa trong $KEY)"
  if [[ "$OPEN_BROWSER" == 1 ]]; then
    (xdg-open "$url" || sensible-browser "$url" || true) >/dev/null 2>&1 &
  fi
}

# --- Reuse a server that is already running ---------------------------------
PORT="${BB_PORT:-19083}"
if health "$PORT"; then
  echo "Server đã chạy sẵn ở cổng $PORT."
  open_game "$PORT"
  exit 0
fi

# --- Start --------------------------------------------------------------------
PORT="$(free_port "$PORT")"
NATIVE_PORT="$(free_port "${BB_NATIVE_PORT:-49119}")"
mkdir -p "$ROOT/runtime/state"
LOG="${BB_LOG:-$ROOT/runtime/state/server.log}"
echo "Bang Bang offline — đang khởi động (Python: $("$PY" --version))"

BB_DATABASE="$DB" BB_ACCELERATION=auto BB_LAUNCH_ID="play-$$" \
  "$PY" -I -B -X utf8 "$ROOT/server/app.py" --bind 127.0.0.1 --port "$PORT" \
  --native-port "$NATIVE_PORT" --enable-admin-buff --admin-key-file "$KEY" --log-level WARNING \
  >"$LOG" 2>&1 &
SERVER=$!
stop() {
  trap - EXIT INT TERM
  echo; echo "Đang dừng server…"
  kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null || true
  echo "Đã dừng."
  exit 0
}
trap stop EXIT INT TERM

for _ in $(seq 1 60); do
  if health "$PORT"; then
    echo "SẴN SÀNG. Giữ cửa sổ này mở khi chơi; Ctrl+C để dừng."
    open_game "$PORT"
    wait "$SERVER"
    exit $?
  fi
  if ! kill -0 "$SERVER" 2>/dev/null; then
    echo "Server không khởi động được. Log:"; tail -20 "$LOG"; exit 1
  fi
  sleep 0.5
done
echo "Chưa sẵn sàng sau 30 giây. Log: $LOG"; tail -20 "$LOG"; exit 1
