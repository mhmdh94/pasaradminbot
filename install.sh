#!/bin/bash

# ============================================================
#  PasarAdminBot Installer
#  ربات خرید حجم برای پنل پاسارگارد
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
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║           PasarAdminBot - Installer                      ║"
    echo "║     ربات خرید حجم برای پنل پاسارگارد                     ║"
    echo "║     github.com/mhmdh94/pasaradminbot                     ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}[ERROR] این اسکریپت باید با دسترسی root اجرا شود.${NC}"
        echo "لطفاً با دستور زیر اجرا کنید: sudo bash install.sh"
        exit 1
    fi
}

check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        echo -e "${YELLOW}[WARNING] این اسکریپت برای اوبونتو طراحی شده. ادامه می‌دهید؟ (y/n)${NC}"
        read -r ans
        if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
            exit 1
        fi
    fi
}

install_dependencies() {
    echo -e "${BLUE}[*] به‌روزرسانی سیستم و نصب پیش‌نیازها...${NC}"
    apt-get update -y
    apt-get install -y python3 python3-pip python3-venv git curl wget unzip software-properties-common

    # Ensure python3 is available
    if ! command -v python3 &>/dev/null; then
        echo -e "${RED}[ERROR] python3 نصب نشد.${NC}"
        exit 1
    fi
    echo -e "${GREEN}[✓] پیش‌نیازها نصب شدند.${NC}"
}

clone_or_copy_bot() {
    echo -e "${BLUE}[*] آماده‌سازی پوشه ربات...${NC}"

    if [ -d "$BOT_DIR" ]; then
        echo -e "${YELLOW}[!] پوشه $BOT_DIR از قبل وجود دارد.${NC}"
        echo -e "آیا می‌خواهید آن را حذف و از نو نصب کنید؟ (y/n)"
        read -r ans
        if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
            systemctl stop $SERVICE_NAME 2>/dev/null || true
            rm -rf "$BOT_DIR"
        else
            echo -e "${YELLOW}نصب لغو شد.${NC}"
            exit 0
        fi
    fi

    mkdir -p "$BOT_DIR"

    # If running from the extracted source (current directory has bot/)
    if [ -d "./bot" ] && [ -f "./bot/main.py" ]; then
        echo -e "${BLUE}[*] کپی فایل‌های منبع از مسیر فعلی...${NC}"
        cp -r ./bot ./requirements.txt ./install.sh "$BOT_DIR/" 2>/dev/null || true
        cp -r ./.env.example "$BOT_DIR/" 2>/dev/null || true
        cp -r ./* "$BOT_DIR/" 2>/dev/null || true
    else
        # Clone from GitHub
        echo -e "${BLUE}[*] کلون از گیت‌هاب ($GITHUB_REPO)...${NC}"
        echo -e "${YELLOW}اگر ریپو خصوصی است، توکن گیت‌هاب را وارد کنید (در غیر این صورت Enter بزنید):${NC}"
        read -r GH_TOKEN

        TMP_CLONE="/tmp/pasaradminbot_clone_$$"
        rm -rf "$TMP_CLONE"

        if [ -n "$GH_TOKEN" ]; then
            git clone "https://${GH_TOKEN}@github.com/${GITHUB_REPO}.git" "$TMP_CLONE"
        else
            git clone "https://github.com/${GITHUB_REPO}.git" "$TMP_CLONE"
        fi

        if [ ! -d "$TMP_CLONE/bot" ]; then
            echo -e "${RED}[ERROR] کلون ناموفق بود یا ساختار پروژه اشتباه است.${NC}"
            rm -rf "$TMP_CLONE"
            exit 1
        fi

        cp -r "$TMP_CLONE"/* "$BOT_DIR/"
        rm -rf "$TMP_CLONE"
    fi

    mkdir -p "$BOT_DIR/data"
    chmod -R 755 "$BOT_DIR"
    echo -e "${GREEN}[✓] فایل‌ها آماده شدند.${NC}"
}

create_venv_and_install() {
    echo -e "${BLUE}[*] ساخت محیط مجازی و نصب پکیج‌ها...${NC}"
    cd "$BOT_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    echo -e "${GREEN}[✓] پکیج‌های پایتون نصب شدند.${NC}"
}

get_config() {
    echo -e "${CYAN}"
    echo "════════════════════════════════════════"
    echo "          تنظیمات ربات"
    echo "════════════════════════════════════════"
    echo -e "${NC}"

    # Bot Token
    while true; do
        echo -e "${YELLOW}توکن ربات را از @BotFather وارد کنید:${NC}"
        read -r BOT_TOKEN
        if [ -n "$BOT_TOKEN" ]; then
            break
        fi
        echo -e "${RED}توکن نمی‌تواند خالی باشد.${NC}"
    done

    # Admin ID
    while true; do
        echo -e "${YELLOW}آیدی عددی ادمین را وارد کنید (از @userinfobot بگیرید):${NC}"
        read -r ADMIN_ID
        if [[ "$ADMIN_ID" =~ ^[0-9]+$ ]]; then
            break
        fi
        echo -e "${RED}آیدی باید عدد باشد.${NC}"
    done

    # Card Number
    echo -e "${YELLOW}شماره کارت (برای کارت‌به‌کارت) را وارد کنید:${NC}"
    read -r CARD_NUMBER
    CARD_NUMBER=${CARD_NUMBER:-"6037-XXXX-XXXX-XXXX"}

    # Card Owner
    echo -e "${YELLOW}نام صاحب کارت را وارد کنید:${NC}"
    read -r CARD_OWNER
    CARD_OWNER=${CARD_OWNER:-"نام صاحب کارت"}

    # Backup time
    echo -e "${YELLOW}ساعت بک‌آپ خودکار (۰ تا ۲۳، پیش‌فرض ۳):${NC}"
    read -r BACKUP_HOUR
    BACKUP_HOUR=${BACKUP_HOUR:-3}

    # Write .env
    cat > "$BOT_DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
CARD_NUMBER=$CARD_NUMBER
CARD_OWNER=$CARD_OWNER
BACKUP_HOUR=$BACKUP_HOUR
BACKUP_MINUTE=0
EOF

    chmod 600 "$BOT_DIR/.env"
    echo -e "${GREEN}[✓] فایل تنظیمات ساخته شد.${NC}"
}

create_systemd_service() {
    echo -e "${BLUE}[*] ساخت سرویس systemd...${NC}"

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
        echo -e "${GREEN}[✓] سرویس با موفقیت راه‌اندازی شد.${NC}"
    else
        echo -e "${RED}[!] سرویس شروع نشد. لاگ را بررسی کنید:${NC}"
        echo "journalctl -u $SERVICE_NAME -n 50 --no-pager"
    fi
}

show_final_info() {
    echo -e "${GREEN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║              نصب با موفقیت انجام شد!                     ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "📁 مسیر ربات:     ${CYAN}$BOT_DIR${NC}"
    echo -e "🔧 سرویس:         ${CYAN}systemctl status $SERVICE_NAME${NC}"
    echo -e "📋 لاگ‌ها:         ${CYAN}journalctl -u $SERVICE_NAME -f${NC}"
    echo -e "🔄 ری‌استارت:     ${CYAN}systemctl restart $SERVICE_NAME${NC}"
    echo -e "⏹ توقف:          ${CYAN}systemctl stop $SERVICE_NAME${NC}"
    echo ""
    echo -e "${YELLOW}دستورات مفید:${NC}"
    echo "  systemctl status $SERVICE_NAME"
    echo "  journalctl -u $SERVICE_NAME -f"
    echo "  systemctl restart $SERVICE_NAME"
    echo ""
    echo -e "${GREEN}ربات را در تلگرام استارت کنید و پنل + پلن‌ها را اضافه کنید.${NC}"
}

# ---------- Update ----------
update_bot() {
    print_logo
    echo -e "${BLUE}[*] آپدیت ربات...${NC}"

    if [ ! -d "$BOT_DIR" ]; then
        echo -e "${RED}ربات نصب نشده است.${NC}"
        exit 1
    fi

    systemctl stop $SERVICE_NAME 2>/dev/null || true

    if [ -d "./bot" ] && [ -f "./bot/main.py" ]; then
        cp -r ./bot "$BOT_DIR/"
        cp ./requirements.txt "$BOT_DIR/" 2>/dev/null || true
    else
        echo -e "${YELLOW}فایل‌های جدید را در مسیر فعلی قرار دهید یا مسیر را وارد کنید:${NC}"
        read -r SRC_PATH
        if [ -n "$SRC_PATH" ] && [ -d "$SRC_PATH/bot" ]; then
            cp -r "$SRC_PATH/bot" "$BOT_DIR/"
            cp "$SRC_PATH/requirements.txt" "$BOT_DIR/" 2>/dev/null || true
        fi
    fi

    cd "$BOT_DIR"
    source venv/bin/activate
    pip install -r requirements.txt --upgrade
    deactivate

    systemctl start $SERVICE_NAME
    echo -e "${GREEN}[✓] آپدیت انجام شد.${NC}"
}

# ---------- Remove ----------
remove_bot() {
    print_logo
    echo -e "${RED}آیا مطمئن هستید که می‌خواهید ربات را کامل حذف کنید؟ (y/n)${NC}"
    read -r ans
    if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
        echo "لغو شد."
        exit 0
    fi

    systemctl stop $SERVICE_NAME 2>/dev/null || true
    systemctl disable $SERVICE_NAME 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload
    rm -rf "$BOT_DIR"
    echo -e "${GREEN}ربات کامل حذف شد.${NC}"
}

# ---------- Menu ----------
show_menu() {
    print_logo
    echo -e "${CYAN}1)${NC} نصب ربات (Install)"
    echo -e "${CYAN}2)${NC} آپدیت ربات (Update)"
    echo -e "${CYAN}3)${NC} حذف ربات (Remove)"
    echo -e "${CYAN}4)${NC} وضعیت سرویس"
    echo -e "${CYAN}5)${NC} خروج"
    echo ""
    read -p "گزینه را انتخاب کنید [1-5]: " option

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
            ;;
        2)
            check_root
            update_bot
            ;;
        3)
            check_root
            remove_bot
            ;;
        4)
            systemctl status $SERVICE_NAME --no-pager || echo "سرویس نصب نشده"
            ;;
        5)
            exit 0
            ;;
        *)
            echo -e "${RED}گزینه نامعتبر${NC}"
            sleep 1
            show_menu
            ;;
    esac
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
elif [ "$1" == "remove" ]; then
    check_root
    remove_bot
else
    show_menu
fi