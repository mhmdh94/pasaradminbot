#!/bin/bash

# ============================================================
#  PasarAdminBot Installer
#  Volume buyer bot for PasarGuard panel
#  GitHub: https://github.com/mhmdh94/pasaradminbot
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

BOT_DIR="/opt/pasaradminbot"
SERVICE_NAME="pasaradminbot"
PYTHON_BIN="python3"
GITHUB_REPO="mhmdh94/pasaradminbot"

print_logo() {
    clear
    echo -e "${CYAN}"
    echo "============================================================"
    echo "           PasarAdminBot - Installer"
    echo "     Volume buyer bot for PasarGuard panel"
    echo "     github.com/mhmdh94/pasaradminbot"
    echo "============================================================"
    echo -e "${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}[ERROR] This script must be run as root.${NC}"
        echo "Please run: sudo bash install.sh"
        exit 1
    fi
}

check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        echo -e "${YELLOW}[WARNING] This script is designed for Ubuntu. Continue anyway? (y/n)${NC}"
        read -r ans
        if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
            exit 1
        fi
    fi
}

install_dependencies() {
    echo -e "${BLUE}[*] Updating system and installing dependencies...${NC}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y \
        software-properties-common \
        ca-certificates \
        curl wget git unzip \
        build-essential \
        libffi-dev \
        || true

    # Prefer Python 3.12 (works on Ubuntu 22/24/26). Avoid 3.14 — pydantic has no wheels yet.
    ensure_python
    echo -e "${GREEN}[OK] Dependencies ready. Python: $($PYTHON_BIN --version 2>&1)${NC}"
}

ensure_python() {
    # Already have a good version?
    for ver in 3.12 3.11 3.10; do
        if command -v "python${ver}" &>/dev/null; then
            if "python${ver}" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==tuple(map(int,'${ver}'.split('.'))) else 1)" 2>/dev/null; then
                PYTHON_BIN="python${ver}"
                # ensure venv package
                apt-get install -y "python${ver}-venv" "python${ver}-dev" 2>/dev/null || true
                echo -e "${GREEN}[OK] Using existing ${PYTHON_BIN}${NC}"
                return 0
            fi
        fi
    done

    echo -e "${BLUE}[*] Installing Python 3.12 (compatible with bot packages)...${NC}"

    # Ubuntu 24.04 usually has 3.12 in main repos
    if apt-cache show python3.12 &>/dev/null; then
        apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip || true
    fi

    if ! command -v python3.12 &>/dev/null; then
        # deadsnakes PPA for 22.04 / newer with only 3.14
        apt-get install -y software-properties-common
        add-apt-repository -y ppa:deadsnakes/ppa || true
        apt-get update -y
        apt-get install -y python3.12 python3.12-venv python3.12-dev || true
    fi

    if command -v python3.12 &>/dev/null; then
        PYTHON_BIN="python3.12"
        return 0
    fi

    # Fallback 3.11
    if ! command -v python3.11 &>/dev/null; then
        apt-get install -y python3.11 python3.11-venv python3.11-dev 2>/dev/null || true
    fi
    if command -v python3.11 &>/dev/null; then
        PYTHON_BIN="python3.11"
        return 0
    fi

    # Last resort: system python3 if <= 3.13
    if command -v python3 &>/dev/null; then
        PY_MINOR=$($PYTHON_BIN -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 99)
        # use real python3
        PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 99)
        if [ "$PY_MINOR" -le 13 ] 2>/dev/null; then
            PYTHON_BIN="python3"
            apt-get install -y python3-venv python3-dev python3-pip || true
            echo -e "${YELLOW}[!] Using system python3 ($(python3 --version))${NC}"
            return 0
        fi
    fi

    echo -e "${RED}[ERROR] Could not install Python 3.10–3.12. pydantic does not support Python 3.14 yet.${NC}"
    echo -e "${RED}Install python3.12 manually, then re-run installer.${NC}"
    exit 1
}

clone_or_copy_bot() {
    echo -e "${BLUE}[*] Preparing bot directory...${NC}"

    if [ -d "$BOT_DIR" ]; then
        echo -e "${YELLOW}[!] Directory $BOT_DIR already exists.${NC}"
        echo -e "Do you want to remove it and reinstall? (y/n)"
        read -r ans
        if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
            systemctl stop $SERVICE_NAME 2>/dev/null || true
            rm -rf "$BOT_DIR"
        else
            echo -e "${YELLOW}Installation cancelled.${NC}"
            exit 0
        fi
    fi

    mkdir -p "$BOT_DIR"

    # If running from source directory (has bot/)
    if [ -d "./bot" ] && [ -f "./bot/main.py" ]; then
        echo -e "${BLUE}[*] Copying source files from current directory...${NC}"
        cp -r ./bot ./requirements.txt ./install.sh "$BOT_DIR/" 2>/dev/null || true
        cp -r ./.env.example "$BOT_DIR/" 2>/dev/null || true
        cp -r ./* "$BOT_DIR/" 2>/dev/null || true
    else
        # Clone from GitHub (public repo)
        echo -e "${BLUE}[*] Cloning from GitHub ($GITHUB_REPO)...${NC}"

        TMP_CLONE="/tmp/pasaradminbot_clone_$$"
        rm -rf "$TMP_CLONE"

        git clone "https://github.com/${GITHUB_REPO}.git" "$TMP_CLONE"

        if [ ! -d "$TMP_CLONE/bot" ]; then
            echo -e "${RED}[ERROR] Clone failed or project structure is invalid.${NC}"
            rm -rf "$TMP_CLONE"
            exit 1
        fi

        cp -r "$TMP_CLONE"/* "$BOT_DIR/"
        rm -rf "$TMP_CLONE"
    fi

    mkdir -p "$BOT_DIR/data"
    chmod -R 755 "$BOT_DIR"
    echo -e "${GREEN}[OK] Files are ready.${NC}"
}

create_venv_and_install() {
    echo -e "${BLUE}[*] Creating virtualenv with ${PYTHON_BIN} and installing packages...${NC}"
    cd "$BOT_DIR"

    # Remove broken venv if any
    rm -rf venv

    if ! $PYTHON_BIN -m venv venv; then
        echo -e "${YELLOW}[!] venv module missing, installing...${NC}"
        # try to install matching venv package
        VER=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        apt-get install -y "python${VER}-venv" "python${VER}-dev" || apt-get install -y python3-venv
        $PYTHON_BIN -m venv venv
    fi

    # shellcheck disable=SC1091
    source venv/bin/activate

    # Prefer binary wheels — avoid compiling pydantic-core / rust
    export PIP_DISABLE_PIP_VERSION_CHECK=1
    export PIP_DEFAULT_TIMEOUT=120
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install --prefer-binary --no-cache-dir -r requirements.txt

    # quick import check
    python -c "import aiogram, aiosqlite, httpx, pydantic; print('imports ok')"

    deactivate
    echo -e "${GREEN}[OK] Python packages installed with $($PYTHON_BIN --version 2>&1).${NC}"
}

get_config() {
    echo -e "${CYAN}"
    echo "========================================"
    echo "          Bot Configuration"
    echo "========================================"
    echo -e "${NC}"
    echo "Only bot startup info is needed."
    echo "Card, panels, plans and other settings are configured inside the bot."
    echo ""

    # Bot Token
    while true; do
        echo -e "${YELLOW}Enter bot token from @BotFather:${NC}"
        read -r BOT_TOKEN
        if [ -n "$BOT_TOKEN" ]; then
            break
        fi
        echo -e "${RED}Token cannot be empty.${NC}"
    done

    # Admin ID
    while true; do
        echo -e "${YELLOW}Enter admin numeric ID (from @userinfobot):${NC}"
        read -r ADMIN_ID
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        fi
        echo -e "${RED}Admin ID must be a number.${NC}"
    done

    # Write .env (minimal)
    cat > "$BOT_DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
BACKUP_HOUR=3
BACKUP_MINUTE=0
EOF

    chmod 600 "$BOT_DIR/.env"
    echo -e "${GREEN}[OK] Config file created.${NC}"
}

create_systemd_service() {
    echo -e "${BLUE}[*] Creating systemd service...${NC}"

    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=PasarAdminBot - Volume Buyer for PasarGuard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
Environment=PATH=$BOT_DIR/venv/bin:/usr/bin
ExecStart=$BOT_DIR/venv/bin/python -m bot.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME

    sleep 2
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}[OK] Service started successfully.${NC}"
    else
        echo -e "${RED}[!] Service failed to start. Check logs:${NC}"
        echo "journalctl -u $SERVICE_NAME -n 50 --no-pager"
    fi
}

show_final_info() {
    echo -e "${GREEN}"
    echo "============================================================"
    echo "              Installation completed!"
    echo "============================================================"
    echo -e "${NC}"
    echo -e "Bot path:       ${CYAN}$BOT_DIR${NC}"
    echo -e "Service:        ${CYAN}systemctl status $SERVICE_NAME${NC}"
    echo -e "Logs:           ${CYAN}journalctl -u $SERVICE_NAME -f${NC}"
    echo -e "Restart:        ${CYAN}systemctl restart $SERVICE_NAME${NC}"
    echo -e "Stop:           ${CYAN}systemctl stop $SERVICE_NAME${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "  systemctl status $SERVICE_NAME"
    echo "  journalctl -u $SERVICE_NAME -f"
    echo "  systemctl restart $SERVICE_NAME"
    echo ""
    echo -e "${GREEN}Start the bot in Telegram. Configure panel, plans and card payment inside the bot.${NC}"
}

# ---------- Update ----------
update_bot() {
    print_logo
    echo -e "${BLUE}[*] Updating bot...${NC}"

    if [ ! -d "$BOT_DIR" ]; then
        echo -e "${RED}Bot is not installed.${NC}"
        return 1
    fi

    systemctl stop $SERVICE_NAME 2>/dev/null || true

    if [ -d "./bot" ] && [ -f "./bot/main.py" ]; then
        cp -r ./bot "$BOT_DIR/"
        cp ./requirements.txt "$BOT_DIR/" 2>/dev/null || true
    else
        echo -e "${BLUE}[*] Pulling latest from GitHub...${NC}"
        TMP_CLONE="/tmp/pasaradminbot_update_$$"
        rm -rf "$TMP_CLONE"
        git clone "https://github.com/${GITHUB_REPO}.git" "$TMP_CLONE"
        if [ -d "$TMP_CLONE/bot" ]; then
            cp -r "$TMP_CLONE/bot" "$BOT_DIR/"
            cp "$TMP_CLONE/requirements.txt" "$BOT_DIR/" 2>/dev/null || true
        fi
        rm -rf "$TMP_CLONE"
    fi

    (
        cd "$BOT_DIR"
        source venv/bin/activate
        pip install -r requirements.txt --upgrade
        deactivate
    )

    systemctl start $SERVICE_NAME
    echo -e "${GREEN}[OK] Update completed.${NC}"
}

# ---------- Remove ----------
remove_bot() {
    print_logo
    echo -e "${RED}This will COMPLETELY remove:${NC}"
    echo -e "  - systemd service: ${SERVICE_NAME}"
    echo -e "  - bot directory:   ${BOT_DIR}"
    echo -e "  - database & .env inside bot dir"
    echo -e "  - install scripts in /tmp and /root"
    echo -e "  - temp clone folders"
    echo ""
    echo -e "${RED}Are you sure? Type y to confirm: ${NC}"
    read -r ans
    if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
        echo "Cancelled."
        return 0
    fi

    echo -e "${BLUE}[*] Stopping service...${NC}"
    systemctl stop $SERVICE_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true

    echo -e "${BLUE}[*] Removing systemd unit...${NC}"
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    rm -f /etc/systemd/system/${SERVICE_NAME}.service.bak 2>/dev/null || true
    systemctl daemon-reload 2>/dev/null || true
    systemctl reset-failed $SERVICE_NAME 2>/dev/null || true

    echo -e "${BLUE}[*] Removing bot directory ${BOT_DIR}...${NC}"
    rm -rf "$BOT_DIR"
    # alternate paths if ever used
    rm -rf /opt/PasarAdminBot /opt/pasaradminbot /root/pasaradminbot 2>/dev/null || true

    echo -e "${BLUE}[*] Removing installer scripts & temp files...${NC}"
    rm -f /tmp/install.sh /tmp/install_pasar*.sh 2>/dev/null || true
    rm -f /root/install.sh /root/install_pasar*.sh 2>/dev/null || true
    rm -rf /tmp/pasaradminbot_update_* /tmp/pasaradminbot_clone_* 2>/dev/null || true
    # remove this script itself if run from a temp/copied path
    if [ -n "${BASH_SOURCE[0]:-}" ]; then
        SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || echo "${BASH_SOURCE[0]}")"
        case "$SELF" in
            /tmp/*|/root/install.sh|/root/install_pasar*)
                rm -f "$SELF" 2>/dev/null || true
                ;;
        esac
    fi

    echo ""
    echo -e "${GREEN}[OK] Bot and installer files removed completely.${NC}"
    echo -e "${YELLOW}Nothing left related to PasarAdminBot on this server.${NC}"
}

# ---------- Menu ----------
show_menu() {
    while true; do
        # always work from a known directory (update_bot does cd)
        cd /root 2>/dev/null || cd / || true

        print_logo
        echo -e "${CYAN}1)${NC} Install bot"
        echo -e "${CYAN}2)${NC} Update bot"
        echo -e "${CYAN}3)${NC} Remove bot"
        echo -e "${CYAN}4)${NC} Service status"
        echo -e "${CYAN}5)${NC} Restart service"
        echo -e "${CYAN}6)${NC} Exit"
        echo ""
        read -p "Select an option [1-6]: " option

        case $option in
            1)
                check_root
                check_ubuntu
                install_dependencies
                clone_or_copy_bot
                create_venv_and_install
                get_config
                create_systemd_service
                show_final_info
                echo ""
                read -p "Press Enter to return to menu..." _
                ;;
            2)
                check_root
                update_bot
                echo ""
                read -p "Press Enter to return to menu..." _
                ;;
            3)
                check_root
                remove_bot
                echo ""
                echo "Exiting installer."
                exit 0
                ;;
            4)
                systemctl status $SERVICE_NAME --no-pager || echo "Service is not installed"
                echo ""
                read -p "Press Enter to return to menu..." _
                ;;
            5)
                systemctl restart $SERVICE_NAME
                sleep 1
                systemctl status $SERVICE_NAME --no-pager || true
                echo ""
                read -p "Press Enter to return to menu..." _
                ;;
            6)
                echo "Bye."
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid option${NC}"
                sleep 1
                ;;
        esac
    done
}

# Main
if [ "$1" == "install" ]; then
    check_root
    check_ubuntu
    install_dependencies
    clone_or_copy_bot
    create_venv_and_install
    get_config
    create_systemd_service
    show_final_info
elif [ "$1" == "update" ]; then
    check_root
    update_bot
    # after CLI update, open interactive menu
    show_menu
elif [ "$1" == "remove" ]; then
    check_root
    remove_bot
else
    show_menu
fi
