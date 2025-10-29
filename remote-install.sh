#!/usr/bin/env bash

# BA-BAAM! Remote Installation Script
# Usage: curl -s https://raw.githubusercontent.com/henrikenblom/babaam/master/remote-install.sh | bash

set -e  # Exit on error

REPO_URL="https://github.com/henrikenblom/babaam.git"
TEMP_DIR="/tmp/babaam-install-$$"
INSTALL_DIR="$HOME/.local/share/babaam"
BIN_DIR="$HOME/.local/bin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════╗"
echo "║    BA-BAAM! Remote Installer      ║"
echo "║   Kill them. Kill them all.       ║"
echo "╚═══════════════════════════════════╝"
echo -e "${NC}"

# Check for git
echo -e "${YELLOW}Checking git installation...${NC}"
if ! command -v git &> /dev/null; then
    echo -e "${RED}ERROR: git is not installed.${NC}"
    echo "Please install git:"
    echo "  - macOS: brew install git"
    echo "  - Ubuntu/Debian: sudo apt-get install git"
    echo "  - Fedora/RHEL: sudo dnf install git"
    exit 1
fi
echo -e "${GREEN}Found git${NC}"

# Check Python version
echo -e "${YELLOW}Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python 3 is not installed.${NC}"
    echo "Please install Python 3.6 or higher:"
    echo "  - macOS: brew install python3"
    echo "  - Ubuntu/Debian: sudo apt-get install python3 python3-pip"
    echo "  - Fedora/RHEL: sudo dnf install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')

echo -e "${GREEN}Found Python ${PYTHON_VERSION}${NC}"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 6 ]; }; then
    echo -e "${RED}ERROR: Python 3.6 or higher is required.${NC}"
    echo "You have Python ${PYTHON_VERSION}"
    exit 1
fi

# Clone repository to temp directory
echo -e "${YELLOW}Downloading BA-BAAM! from GitHub...${NC}"
rm -rf "$TEMP_DIR"
git clone "$REPO_URL" "$TEMP_DIR" > /dev/null 2>&1 || {
    echo -e "${RED}ERROR: Failed to clone repository.${NC}"
    exit 1
}
echo -e "${GREEN}Repository downloaded successfully!${NC}"

# Create installation directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ -d "$INSTALL_DIR/venv" ]; then
    echo -e "${YELLOW}Removing existing virtual environment...${NC}"
    rm -rf "$INSTALL_DIR/venv"
fi

python3 -m venv "$INSTALL_DIR/venv" || {
    echo -e "${RED}ERROR: Failed to create virtual environment.${NC}"
    exit 1
}
echo -e "${GREEN}Virtual environment created!${NC}"

# Install Python dependencies in virtual environment
echo -e "${YELLOW}Installing Python dependencies...${NC}"
echo -e "${BLUE}(This may take a minute...)${NC}"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip > /dev/null 2>&1
"$INSTALL_DIR/venv/bin/pip" install pynput pygame numpy > /dev/null 2>&1 || {
    echo -e "${RED}ERROR: Failed to install Python dependencies.${NC}"
    echo "You can try installing manually with:"
    echo "  $INSTALL_DIR/venv/bin/pip install pynput pygame numpy"
    rm -rf "$TEMP_DIR"
    exit 1
}
echo -e "${GREEN}Python dependencies installed successfully!${NC}"

# Copy game files
echo -e "${YELLOW}Installing game files...${NC}"
cp "$TEMP_DIR/babaam.py" "$INSTALL_DIR/"
cp "$TEMP_DIR/version.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/babaam.py"
echo -e "${GREEN}Game files installed!${NC}"

# Create launcher script
echo -e "${YELLOW}Creating launcher script...${NC}"
cat > "$BIN_DIR/babaam" << 'LAUNCHER_EOF'
#!/usr/bin/env bash

# BA-BAAM! Launcher Script
INSTALL_DIR="$HOME/.local/share/babaam"

# Check if game is installed
if [ ! -f "$INSTALL_DIR/babaam.py" ]; then
    echo "ERROR: BA-BAAM! is not properly installed."
    echo "Please run the installer again."
    exit 1
fi

# Check if virtual environment exists
if [ ! -f "$INSTALL_DIR/venv/bin/python3" ]; then
    echo "ERROR: Virtual environment is missing."
    echo "Please run the installer again."
    exit 1
fi

# Run the game using virtual environment Python
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/babaam.py"
LAUNCHER_EOF

chmod +x "$BIN_DIR/babaam"
echo -e "${GREEN}Launcher script created!${NC}"

# Clean up temp directory
echo -e "${YELLOW}Cleaning up...${NC}"
rm -rf "$TEMP_DIR"

# Check if ~/.local/bin is in PATH
echo -e "${YELLOW}Checking PATH configuration...${NC}"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "${YELLOW}$HOME/.local/bin is not in your PATH.${NC}"
    echo ""

    # Detect user's shell
    CURRENT_SHELL=$(basename "$SHELL")
    case "$CURRENT_SHELL" in
        bash)
            RC_FILE="$HOME/.bashrc"
            ;;
        zsh)
            RC_FILE="$HOME/.zshrc"
            ;;
        fish)
            RC_FILE="$HOME/.config/fish/config.fish"
            ;;
        *)
            RC_FILE="$HOME/.profile"
            ;;
    esac

    echo -e "${BLUE}Detected shell: ${CURRENT_SHELL}${NC}"
    echo -e "${BLUE}Configuration file: ${RC_FILE}${NC}"
    echo ""
    read -p "Would you like to add $HOME/.local/bin to your PATH in ${RC_FILE}? (y/n): " -n 1 -r < /dev/tty
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Add PATH to rc file
        echo "" >> "$RC_FILE"
        echo "# Added by BA-BAAM! installer" >> "$RC_FILE"
        if [ "$CURRENT_SHELL" = "fish" ]; then
            echo "set -gx PATH \$HOME/.local/bin \$PATH" >> "$RC_FILE"
        else
            echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$RC_FILE"
        fi
        echo -e "${GREEN}PATH added to ${RC_FILE}!${NC}"

        # Add to current PATH
        export PATH="$HOME/.local/bin:$PATH"
        echo -e "${GREEN}PATH updated for current session!${NC}"
        PATH_CONFIGURED=true
    else
        echo -e "${YELLOW}Skipping PATH configuration.${NC}"
        echo "You can run the game directly with:"
        echo -e "${GREEN}  $HOME/.local/bin/babaam${NC}"
        PATH_CONFIGURED=false
    fi
else
    PATH_CONFIGURED=true
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation Complete!           ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════╝${NC}"
echo ""
echo "Game installed to: $INSTALL_DIR"
echo "Launcher script: $BIN_DIR/babaam"
echo ""
echo -e "${YELLOW}Tip: For the best experience, make sure your terminal has a size of 80x24${NC}"
echo ""
if [ "$PATH_CONFIGURED" = true ]; then
    echo -e "${BLUE}To start the game, simply run:${NC}"
    echo -e "${GREEN}  babaam${NC}"
else
    echo -e "${BLUE}To start the game, run:${NC}"
    echo -e "${GREEN}  $HOME/.local/bin/babaam${NC}"
fi
echo ""
echo -e "${YELLOW}Kill them. Kill them all.${NC}"
echo ""
