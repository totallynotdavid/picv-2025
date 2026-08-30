#!/usr/bin/env bash
set -euo pipefail

# Installs the local scientific runtime that mise/uv/Bun do not manage:
# GMT, the TTT SDK, Intel Fortran (ifx), and prebuilt TSDHN model executables.
#
# Project language tooling is intentionally out of scope. Use:
#   mise install
#   mise run install
#   mise run web-install

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TSDHN_TOOLS_DIR:-$ROOT_DIR/.tsdhn/tools}"
ENV_FILE="$ROOT_DIR/.tsdhn/env"

TTT_SDK_REPO="${TTT_SDK_REPO:-https://gitlab.com/totallynotdavid/tttapi/}"
GMT_MIN_VERSION="${GMT_MIN_VERSION:-6.5.0}"

INSTALL_APT=false
INSTALL_GMT_SOURCE=false
INSTALL_TTT=false
INSTALL_IFX=false
BUILD_TOOLS=false
ASSUME_YES=false

log_info() { printf "\n==> %s\n" "$1"; }
log_ok() { printf "ok: %s\n" "$1"; }
log_warn() { printf "warn: %s\n" "$1"; }
log_error() { printf "error: %s\n" "$1" >&2; }

usage() {
    cat <<EOF
Usage: ./setup.sh [options]

Options:
  --yes              Run without confirmation prompts.
  --skip-apt         Do not install missing apt packages.
  --skip-gmt-source  Do not build GMT from source if apt GMT is too old.
  --skip-ttt         Do not install ttt_client.
  --skip-ifx         Do not install Intel Fortran Essentials.
  --skip-tools       Do not compile fault_plane/deform/tsunami. These
                     legacy binaries are used only by the parity suite
                     (mise run test-parity); the pipeline itself is pure
                     Python and does not need them.
  --tools-dir DIR    Directory for compiled model executables.
  -h, --help         Show this help.

Environment:
  TTT_SDK_REPO       TTT SDK git repository. Default: $TTT_SDK_REPO
  GMT_MIN_VERSION    Minimum accepted GMT version. Default: $GMT_MIN_VERSION
  TSDHN_TOOLS_DIR    Output directory for compiled tools. Default: $TOOLS_DIR
EOF
}

while (($#)); do
    case "$1" in
        --yes)
            ASSUME_YES=true
            ;;
        --skip-apt)
            INSTALL_APT=skip
            ;;
        --skip-gmt-source)
            INSTALL_GMT_SOURCE=skip
            ;;
        --skip-ttt)
            INSTALL_TTT=skip
            ;;
        --skip-ifx)
            INSTALL_IFX=skip
            ;;
        --skip-tools)
            BUILD_TOOLS=skip
            ;;
        --tools-dir)
            shift
            TOOLS_DIR="${1:?--tools-dir requires a directory}"
            ENV_FILE="$ROOT_DIR/.tsdhn/env"
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 2
            ;;
    esac
    shift
done

cmd_exists() {
    command -v "$1" >/dev/null 2>&1
}

apt_installed() {
    dpkg -s "$1" >/dev/null 2>&1
}

run() {
    log_info "$1"
    shift
    "$@"
}

version_at_least() {
    local have="$1"
    local need="$2"
    [[ "$(printf "%s\n%s\n" "$need" "$have" | sort -V | head -n1)" == "$need" ]]
}

gmt_version() {
    gmt --version 2>/dev/null | awk '{print $1}'
}

ttt_version() {
    ttt_client 2>&1 | sed -n 's/.*ttt API version \([0-9.]*\).*/\1/p' | head -n1
}

load_ifx_env() {
    if cmd_exists ifx; then
        return 0
    fi

    local setvars
    for setvars in \
        /opt/intel/oneapi/setvars.sh \
        "$HOME/intel/oneapi/setvars.sh"
    do
        if [[ -f "$setvars" ]]; then
            # shellcheck disable=SC1090
            source "$setvars" >/dev/null 2>&1 || true
            cmd_exists ifx && return 0
        fi
    done

    return 1
}

add_bashrc_line() {
    local marker="$1"
    local line="$2"

    touch "$HOME/.bashrc"
    if ! grep -Fq "$line" "$HOME/.bashrc"; then
        {
            printf "\n# %s\n" "$marker"
            printf "%s\n" "$line"
        } >> "$HOME/.bashrc"
    fi
}

APT_PACKAGES=(
    build-essential
    ca-certificates
    cmake
    csh
    curl
    ffmpeg
    fontconfig
    gdal-bin
    ghostscript
    git
    git-lfs
    gnupg
    graphicsmagick
    gmt
    gmt-dcw
    gmt-gshhg
    libblas-dev
    libcurl4
    libfftw3-dev
    libgdal-dev
    liblapack-dev
    libnetcdf-dev
    libpcre3
    lsb-release
    make
    pkg-config
    ps2eps
    wget
    xz-utils
)

missing_apt=()
for pkg in "${APT_PACKAGES[@]}"; do
    apt_installed "$pkg" || missing_apt+=("$pkg")
done

if [[ "$INSTALL_APT" != "skip" && ${#missing_apt[@]} -gt 0 ]]; then
    INSTALL_APT=true
fi

if cmd_exists gmt; then
    current_gmt="$(gmt_version)"
    if version_at_least "$current_gmt" "$GMT_MIN_VERSION"; then
        log_ok "GMT $current_gmt is installed"
    else
        log_warn "GMT $current_gmt is older than $GMT_MIN_VERSION"
        [[ "$INSTALL_GMT_SOURCE" != "skip" ]] && INSTALL_GMT_SOURCE=true
    fi
else
    log_warn "GMT is not installed"
    [[ "$INSTALL_APT" != "skip" ]] && INSTALL_APT=true
fi

if cmd_exists ttt_client; then
    current_ttt="$(ttt_version)"
    log_ok "ttt_client is installed${current_ttt:+ ($current_ttt)}"
else
    log_warn "ttt_client is not installed"
    [[ "$INSTALL_TTT" != "skip" ]] && INSTALL_TTT=true
fi

if load_ifx_env; then
    log_ok "ifx is installed ($(ifx --version | head -n1))"
else
    log_warn "ifx is not installed"
    [[ "$INSTALL_IFX" != "skip" ]] && INSTALL_IFX=true
fi

if [[ "$BUILD_TOOLS" != "skip" ]]; then
    if [[ ! -x "$TOOLS_DIR/fault_plane" || ! -x "$TOOLS_DIR/deform" || ! -x "$TOOLS_DIR/tsunami" ]]; then
        BUILD_TOOLS=true
    fi
fi

if [[ "$INSTALL_APT" != true &&
      "$INSTALL_GMT_SOURCE" != true &&
      "$INSTALL_TTT" != true &&
      "$INSTALL_IFX" != true &&
      "$BUILD_TOOLS" != true ]]; then
    log_ok "Scientific runtime is already installed"
    exit 0
fi

log_info "Planned actions"
[[ "$INSTALL_APT" == true ]] && printf -- "- Install missing apt packages: %s\n" "${missing_apt[*]:-runtime prerequisites}"
[[ "$INSTALL_GMT_SOURCE" == true ]] && printf -- "- Build GMT from source because installed GMT is too old\n"
[[ "$INSTALL_TTT" == true ]] && printf -- "- Install TTT SDK from %s\n" "$TTT_SDK_REPO"
[[ "$INSTALL_IFX" == true ]] && printf -- "- Install Intel Fortran Essentials from Intel's apt repository\n"
[[ "$BUILD_TOOLS" == true ]] && printf -- "- Compile model executables into %s\n" "$TOOLS_DIR"

if ! $ASSUME_YES; then
    printf "\nContinue? [y/N] "
    read -r reply
    case "$reply" in
        y|Y|yes|YES) ;;
        *) log_info "Aborted"; exit 1 ;;
    esac
fi

if [[ "$INSTALL_APT" == true ]]; then
    run "Updating apt metadata" sudo apt-get update
    run "Installing apt runtime prerequisites" sudo apt-get install -y --no-install-recommends "${missing_apt[@]}"
    run "Enabling git-lfs" sudo git lfs install --system
fi

if [[ "$INSTALL_IFX" == true ]]; then
    run "Adding Intel oneAPI apt key" bash -c \
        'wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/oneapi-archive-keyring.gpg >/dev/null'
    run "Adding Intel oneAPI apt repository" bash -c \
        'echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneAPI.list >/dev/null'
    run "Updating apt metadata for oneAPI" sudo apt-get update
    run "Installing Intel Fortran Essentials" sudo apt-get install -y --no-install-recommends intel-fortran-essentials

    add_bashrc_line "Intel oneAPI" '[ -f /opt/intel/oneapi/setvars.sh ] && source /opt/intel/oneapi/setvars.sh > /dev/null'
    load_ifx_env || {
        log_error "ifx was installed but is not available in this shell"
        exit 1
    }
fi

if [[ "$INSTALL_GMT_SOURCE" == true ]]; then
    GMT_BUILD_DIR="$(mktemp -d)"
    trap 'rm -rf "$GMT_BUILD_DIR"' EXIT

    run "Cloning GMT source" git clone --depth 50 https://github.com/GenericMappingTools/gmt.git "$GMT_BUILD_DIR/gmt"
    run "Downloading GSHHG data" wget -q -P "$GMT_BUILD_DIR" https://github.com/GenericMappingTools/gshhg-gmt/releases/download/2.3.7/gshhg-gmt-2.3.7.tar.gz
    run "Downloading DCW data" wget -q -P "$GMT_BUILD_DIR" https://github.com/GenericMappingTools/dcw-gmt/releases/download/2.2.0/dcw-gmt-2.2.0.tar.gz
    run "Extracting GSHHG data" tar -xzf "$GMT_BUILD_DIR/gshhg-gmt-2.3.7.tar.gz" -C "$GMT_BUILD_DIR"
    run "Extracting DCW data" tar -xzf "$GMT_BUILD_DIR/dcw-gmt-2.2.0.tar.gz" -C "$GMT_BUILD_DIR"

    cat > "$GMT_BUILD_DIR/gmt/cmake/ConfigUser.cmake" <<EOF
set (CMAKE_INSTALL_PREFIX "/usr/local")
set (GSHHG_ROOT "$GMT_BUILD_DIR/gshhg-gmt-2.3.7")
set (DCW_ROOT "$GMT_BUILD_DIR/dcw-gmt-2.2.0")
EOF

    run "Configuring GMT" cmake -S "$GMT_BUILD_DIR/gmt" -B "$GMT_BUILD_DIR/gmt/build" -G Ninja
    run "Building GMT" cmake --build "$GMT_BUILD_DIR/gmt/build"
    run "Installing GMT" sudo cmake --build "$GMT_BUILD_DIR/gmt/build" --target install
    run "Refreshing dynamic linker cache" sudo ldconfig
fi

if [[ "$INSTALL_TTT" == true ]]; then
    TTT_BUILD_DIR="$(mktemp -d)"
    trap 'rm -rf "${GMT_BUILD_DIR:-}" "${TTT_BUILD_DIR:-}"' EXIT

    run "Cloning TTT SDK" git clone --depth 1 "$TTT_SDK_REPO" "$TTT_BUILD_DIR/tttapi"
    run "Configuring and compiling TTT SDK" make -C "$TTT_BUILD_DIR/tttapi" config compile
    run "Installing TTT SDK" sudo make -C "$TTT_BUILD_DIR/tttapi" install datadir docs
    run "Testing and cleaning TTT SDK" make -C "$TTT_BUILD_DIR/tttapi" test clean
fi

if [[ "$BUILD_TOOLS" == true ]]; then
    load_ifx_env || {
        log_error "Cannot compile model tools without ifx"
        exit 1
    }

    mkdir -p "$TOOLS_DIR"
    run "Compiling fault_plane" ifx -parallel "$ROOT_DIR/model/fault_plane.f90" -o "$TOOLS_DIR/fault_plane"
    run "Compiling deform" ifx -parallel "$ROOT_DIR/model/def_oka.f" -o "$TOOLS_DIR/deform"
    run "Compiling tsunami" ifx -parallel -qopenmp "$ROOT_DIR/model/tsunami1.for" -o "$TOOLS_DIR/tsunami"
    chmod +x "$TOOLS_DIR/fault_plane" "$TOOLS_DIR/deform" "$TOOLS_DIR/tsunami"
fi

mkdir -p "$(dirname "$ENV_FILE")"
cat > "$ENV_FILE" <<EOF
TSDHN_MODEL_DIR="$ROOT_DIR/model"
TSDHN_TOOLS_DIR="$TOOLS_DIR"
EOF

log_info "Verifying runtime"

fail=false
if ! cmd_exists gmt; then
    log_error "gmt is not available"
    fail=true
elif ! version_at_least "$(gmt_version)" "$GMT_MIN_VERSION"; then
    log_error "gmt $(gmt_version) is older than $GMT_MIN_VERSION"
    fail=true
else
    log_ok "gmt $(gmt_version)"
fi

if ! cmd_exists ttt_client; then
    log_error "ttt_client is not available"
    fail=true
else
    current_ttt="$(ttt_version)"
    log_ok "ttt_client${current_ttt:+ $current_ttt}"
fi

if ! load_ifx_env; then
    log_error "ifx is not available"
    fail=true
else
    log_ok "ifx"
fi

for exe in fault_plane deform tsunami; do
    if [[ ! -x "$TOOLS_DIR/$exe" ]]; then
        log_error "$TOOLS_DIR/$exe is missing or not executable"
        fail=true
    else
        log_ok "$TOOLS_DIR/$exe"
    fi
done

if $fail; then
    log_error "Runtime setup is incomplete"
    exit 1
fi

log_ok "Runtime setup complete"
printf "\nFor local CLI/API runs, load runtime paths with:\n"
printf "  source %s\n" "$ENV_FILE"
printf "\nProject dependencies are still managed separately:\n"
printf "  mise install && mise run install && mise run web-install\n"
