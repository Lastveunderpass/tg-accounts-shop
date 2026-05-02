#!/usr/bin/env bash
# Один-в-один установщик: ставит docker (если нужно), клонит репо, запрашивает
# обязательные .env-переменные, поднимает docker compose, накатывает миграции.
#
# Запуск:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Lastveunderpass/tg-accounts-shop/main/install.sh)
#
# Идемпотентен: повторный запуск = git pull + rebuild + migrate.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Lastveunderpass/tg-accounts-shop.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/tg-shop}"
BRANCH="${BRANCH:-main}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
info() { printf "\033[36m[i]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[!]\033[0m %s\n" "$*"; }
err()  { printf "\033[31m[x]\033[0m %s\n" "$*" >&2; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || { err "не найдена команда $1"; exit 1; }
}

ensure_root_or_sudo() {
    if [ "$(id -u)" -ne 0 ]; then
        if ! command -v sudo >/dev/null 2>&1; then
            err "Запусти от root или установи sudo."
            exit 1
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        info "docker уже установлен"
        return
    fi
    info "Устанавливаю Docker через get.docker.com..."
    curl -fsSL https://get.docker.com | $SUDO sh
    if ! docker compose version >/dev/null 2>&1; then
        warn "docker compose plugin не найден. Установка через apt..."
        $SUDO apt-get update -y
        $SUDO apt-get install -y docker-compose-plugin || true
    fi
    if ! docker compose version >/dev/null 2>&1; then
        err "docker compose plugin не доступен. Установи вручную."
        exit 1
    fi
}

clone_or_update_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Обновляю репозиторий в $INSTALL_DIR"
        $SUDO git -C "$INSTALL_DIR" fetch --all --prune
        $SUDO git -C "$INSTALL_DIR" checkout "$BRANCH"
        $SUDO git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
    else
        info "Клонирую $REPO_URL в $INSTALL_DIR"
        $SUDO mkdir -p "$INSTALL_DIR"
        $SUDO git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
}

prompt_var() {
    local var="$1" prompt="$2" default="${3:-}" silent="${4:-0}"
    local cur
    cur=$(grep -E "^${var}=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true)
    if [ -n "$cur" ]; then
        info "$var уже задан, пропускаю"
        eval "$var='$cur'"
        return
    fi
    local val=""
    if [ "$silent" = "1" ]; then
        read -r -s -p "$prompt: " val; echo ""
    else
        if [ -n "$default" ]; then
            read -r -p "$prompt [$default]: " val
            val="${val:-$default}"
        else
            read -r -p "$prompt: " val
        fi
    fi
    eval "$var=\"\$val\""
}

write_env() {
    info "Готовлю .env"
    if [ ! -f "$ENV_FILE" ]; then
        $SUDO cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
    fi

    prompt_var BOT_TOKEN "Telegram BOT_TOKEN (от @BotFather)"
    prompt_var ADMIN_ID "Telegram ID админа (число)"
    prompt_var SUPPORT_USERNAME "Username саппорта (@your_username)"
    prompt_var CRYPTOBOT_TOKEN "CryptoBot Pay token"

    # генерация webhook secret, если пустой
    local cur_secret
    cur_secret=$(grep -E "^CRYPTOBOT_WEBHOOK_SECRET=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true)
    if [ -z "$cur_secret" ]; then
        local gen
        gen=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)
        $SUDO sed -i.bak "s|^CRYPTOBOT_WEBHOOK_SECRET=.*|CRYPTOBOT_WEBHOOK_SECRET=$gen|" "$ENV_FILE"
    fi

    # запись пользовательских значений
    set_env_var() {
        local key="$1" val="$2"
        if grep -qE "^${key}=" "$ENV_FILE"; then
            local escaped
            escaped=$(printf '%s\n' "$val" | sed -e 's/[\/&|]/\\&/g')
            $SUDO sed -i.bak "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
        else
            echo "${key}=${val}" | $SUDO tee -a "$ENV_FILE" >/dev/null
        fi
    }
    set_env_var BOT_TOKEN "$BOT_TOKEN"
    set_env_var ADMIN_ID "$ADMIN_ID"
    set_env_var SUPPORT_USERNAME "$SUPPORT_USERNAME"
    set_env_var CRYPTOBOT_TOKEN "$CRYPTOBOT_TOKEN"

    $SUDO rm -f "${ENV_FILE}.bak" || true
}

run_compose() {
    info "Собираю и поднимаю контейнер..."
    (cd "$INSTALL_DIR" && $SUDO docker compose build)
    (cd "$INSTALL_DIR" && $SUDO docker compose up -d)
    # Миграции Alembic накатываются автоматически в entrypoint контейнера
    # (scripts/entrypoint.sh) перед стартом приложения, ручной шаг здесь не нужен.
    info "Готово."
}

main() {
    ensure_root_or_sudo
    require_cmd curl
    require_cmd git
    install_docker
    clone_or_update_repo
    ENV_FILE="$INSTALL_DIR/.env"
    write_env
    run_compose

    bold "✅ Установка завершена."
    echo "Папка проекта: $INSTALL_DIR"
    echo "Управление:"
    echo "  cd $INSTALL_DIR && docker compose logs -f"
    echo "  cd $INSTALL_DIR && docker compose restart app"
    echo ""
    echo "Открой бота в Telegram и нажми /start от админ-аккаунта."
}

main "$@"
