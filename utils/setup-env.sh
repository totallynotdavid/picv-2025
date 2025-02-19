#!/bin/bash
set -e

# Detect WSL environment
if [[ -f /proc/sys/fs/binfmt_misc/WSLInterop ]]; then
    IS_WSL=true
    echo "Detected WSL environment"
else
    IS_WSL=false
    echo "Detected native Ubuntu environment"
fi

# System update
echo "Updating system packages..."
sudo apt update -y && sudo apt upgrade -y

# Install pyenv
echo "Installing pyenv..."
curl -fsSL https://pyenv.run | bash

# Configure pyenv in .bashrc
echo "Configuring pyenv..."
if $IS_WSL; then
    cat << 'EOF' >> ~/.bashrc
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
EOF
else
    cat << 'EOF' >> ~/.bashrc
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
EOF
fi

source ~/.bashrc

# Install Python build dependencies
echo "Installing Python build dependencies..."
sudo apt install -y build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev \
    libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev tk-dev

# Install Python 3.12 using pyenv
echo "Installing Python 3.12..."
pyenv install 3.12
pyenv global 3.12

# Verify Python installation
echo "Verifying Python installation..."
python3 -V
pip3 -V

# Install Poetry
echo "Installing Poetry..."
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
poetry --version

# Install TTT SDK dependencies
echo "Installing TTT SDK dependencies..."
sudo apt install -y git-lfs cmake

# Install TTT SDK
echo "Installing TTT SDK..."
git clone https://gitlab.com/totallynotdavid/tttapi/
cd tttapi
make config compile
sudo make install datadir docs
make test clean
cd ..

# Install TeXLive
echo "Installing TeXLive..."
cd /tmp
wget https://mirror.ctan.org/systems/texlive/tlnet/install-tl-unx.tar.gz
zcat < install-tl-unx.tar.gz | tar xf -
cd install-tl-2*

cat > texlive.profile << 'EOF'
selected_scheme scheme-basic
tlpdbopt_autobackup 0
tlpdbopt_install_docfiles 0
tlpdbopt_install_srcfiles 0
EOF

perl ./install-tl --profile=texlive.profile \
                  --texdir "$HOME/texlive" \
                  --texuserdir "$HOME/.texlive" \
                  --no-interaction

echo 'export PATH="$HOME/texlive/bin/x86_64-linux:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Install LaTeX packages
echo "Installing LaTeX packages..."
tlmgr update --self
tlmgr install babel-spanish hyphen-spanish booktabs

# Install additional dependencies
echo "Installing additional dependencies..."
sudo apt install -y gfortran redis-server gmt gmt-dcw gmt-gshhg ps2eps csh

# Configure Redis
echo "Configuring Redis..."
sudo sed -i 's/^# \?supervised \(no\|auto\)/supervised systemd/' /etc/redis/redis.conf
sudo systemctl restart redis-server

echo "Environment setup completed successfully!"