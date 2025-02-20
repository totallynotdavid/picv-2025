#!/bin/bash
set -eo pipefail

# Append a configuration block with a unique marker to a file.
append_config_block() {
    local marker="$1"   # e.g., "# [PYENV CONFIGURATION]"
    local config="$2"   # block to append
    local file="$3"
    [ -f "$file" ] || touch "$file"
    if ! grep -Fq "$marker" "$file"; then
        echo -e "\n$marker" >> "$file"
        echo -e "$config" >> "$file"
    fi
}

# WSL appends Windows path to the PATH variable, 
# which can cause issues with pyenv if pyenv is
# installed in both Windows and WSL
if [[ -f /proc/sys/fs/binfmt_misc/WSLInterop ]]; then
    PYENV_CFG="export PYENV_ROOT=\"\$HOME/.pyenv\"
export PATH=\"\$PYENV_ROOT/bin:\$PATH\"
eval \"\$(pyenv init -)\""
else
    PYENV_CFG="export PYENV_ROOT=\"\$HOME/.pyenv\"
[[ -d \$PYENV_ROOT/bin ]] && export PATH=\"\$PYENV_ROOT/bin:\$PATH\"
eval \"\$(pyenv init - bash)\""
fi

sudo apt update -y && sudo apt upgrade -y

REQUIRED_PKGS=(
    build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev
    libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev tk-dev
    git-lfs cmake gfortran redis-server gmt gmt-dcw gmt-gshhg ps2eps csh
)
missing_pkgs=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        missing_pkgs+=("$pkg")
    fi
done
if (( ${#missing_pkgs[@]} > 0 )); then
    sudo apt install -y "${missing_pkgs[@]}"
fi

BASHRC=~/.bashrc

if ! command -v pyenv &>/dev/null; then
    append_config_block "# [PYENV CONFIGURATION]" "$PYENV_CFG" "$BASHRC"
fi

if ! command -v poetry &>/dev/null; then
    append_config_block "# [POETRY PATH]" 'export PATH="$HOME/.local/bin:$PATH"' "$BASHRC"
fi

if ! command -v tex &>/dev/null; then
    append_config_block "# [TEXLIVE PATH]" 'export PATH="$HOME/texlive/bin/x86_64-linux:$PATH"' "$BASHRC"
fi

source "$BASHRC"

if [[ ! -d "$HOME/.pyenv" ]]; then
    curl -fsSL https://pyenv.run | bash
    # We have to double make sure that pyenv is available in the current shell
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init -)"
    pyenv install -s 3.12
    pyenv global 3.12
fi

if ! command -v poetry &>/dev/null; then
    curl -sSL https://install.python-poetry.org | python3 -
fi

if ! command -v ttt_client &>/dev/null; then
    echo -e "\n📦 Installing TTT SDK..."
    TMP_DIR=$(mktemp -d)
    git clone -q https://gitlab.com/totallynotdavid/tttapi/ "$TMP_DIR/tttapi"
    (
        cd "$TMP_DIR/tttapi"
        make config compile
        sudo make install datadir docs
        make test clean
    )
    rm -rf "$TMP_DIR"
fi

if [[ ! -d "$HOME/texlive" ]]; then
    TMP_TL=$(mktemp -d)
    pushd "$TMP_TL" > /dev/null
    wget -q https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz
    tar -xzf install-tl-unx.tar.gz
    cd install-tl-2*/
    perl ./install-tl \
        --profile=- \
        --texdir="$HOME/texlive" \
        --texuserdir="$HOME/.texlive" \
        --no-interaction <<< $'selected_scheme scheme-basic\ntlpdbopt_autobackup 0\ntlpdbopt_install_docfiles 0\ntlpdbopt_install_srcfiles 0'
    tlmgr install babel-spanish hyphen-spanish booktabs --verify-repo=none --quiet
    popd > /dev/null
    rm -rf "$TMP_TL"
fi

REDIS_CONF="/etc/redis/redis.conf"
if ! sudo grep -q "^supervised systemd" "$REDIS_CONF"; then
    sudo cp "$REDIS_CONF" "${REDIS_CONF}.bak"
    sudo sed -i '/^# *supervised/s/^# *//' "$REDIS_CONF"
    sudo sed -i 's/^supervised .*/supervised systemd/' "$REDIS_CONF"
    sudo systemctl restart redis-server
fi

echo -e "\n✅ Environment configured successfully"
