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
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv git curl wget unzip software-properties-common

    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}[ERROR] python3 was not installed.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[OK] Dependencies installed.${NC}"
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
    echo -e "${BLUE}[*] Creating virtualenv and installing Python packages...${NC}"
    cd "$BOT_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    echo -e "${GREEN}[OK] Python packages installed.${NC}"
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
    echo -e "${RED}Are you sure you want to completely remove the bot? (y/n)${NC}"
    read -r ans
    if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
        echo "Cancelled."
        exit 0
    fi

    systemctl stop $SERVICE_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload
    rm -rf "$BOT_DIR"
    echo -e "${GREEN}Bot removed completely.${NC}"
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
                read -p "Press Enter to return to menu..." _
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
