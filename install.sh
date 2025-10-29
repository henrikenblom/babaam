#!/usr/bin/env bash

# BA-BAAM! Installation Script
# Version 1.0.0

set -e  # Exit on error

GAME_NAME="BA-BAAM!"
INSTALL_DIR="$HOME/.local/share/babaam"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔═══════════════════════════════════╗"
echo "║         BA-BAAM! Installer        ║"
echo "║   Kill them. Kill them all.       ║"
echo "╚═══════════════════════════════════╝"
echo -e "${NC}"

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

# Check pip
echo -e "${YELLOW}Checking pip installation...${NC}"
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}ERROR: pip3 is not installed.${NC}"
    echo "Please install pip3 for your system."
    exit 1
fi
echo -e "${GREEN}Found pip3${NC}"

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
pip3 install --user pynput pygame numpy || {
    echo -e "${RED}ERROR: Failed to install Python dependencies.${NC}"
    echo "You can try installing manually with:"
    echo "  pip3 install --user pynput pygame numpy"
    exit 1
}
echo -e "${GREEN}Python dependencies installed successfully!${NC}"

# Create installation directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Copy game files
echo -e "${YELLOW}Installing game files...${NC}"
cp "$SCRIPT_DIR/babaam.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/version.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/babaam.py"

# Create launcher script
echo -e "${YELLOW}Creating launcher script...${NC}"
cat > "$BIN_DIR/babaam" << 'LAUNCHER_EOF'
#!/usr/bin/env bash

# BA-BAAM! Launcher Script
INSTALL_DIR="$HOME/.local/share/babaam"

# Check if game is installed
if [ ! -f "$INSTALL_DIR/babaam.py" ]; then
    echo "ERROR: BA-BAAM! is not properly installed."
    echo "Please run install.sh again."
    exit 1
fi

# Run the game
cd "$INSTALL_DIR"
exec python3 "$INSTALL_DIR/babaam.py"
LAUNCHER_EOF

chmod +x "$BIN_DIR/babaam"

# Check if ~/.local/bin is in PATH
echo -e "${YELLOW}Checking PATH configuration...${NC}"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo -e "${YELLOW}NOTE: $HOME/.local/bin is not in your PATH.${NC}"
    echo "Add the following line to your ~/.bashrc, ~/.zshrc, or ~/.profile:"
    echo ""
    echo -e "${GREEN}  export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    echo ""
    echo "Then run: source ~/.bashrc (or ~/.zshrc, or ~/.profile)"
    echo ""
    echo "Alternatively, you can run the game directly with:"
    echo -e "${GREEN}  $HOME/.local/bin/babaam${NC}"
    PATH_CONFIGURED=false
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

if [ "$PATH_CONFIGURED" = true ]; then
    echo -e "${BLUE}To start the game, simply run:${NC}"
    echo -e "${GREEN}  babaam${NC}"
else
    echo -e "${BLUE}To start the game after configuring PATH, run:${NC}"
    echo -e "${GREEN}  babaam${NC}"
    echo ""
    echo -e "${BLUE}Or run directly:${NC}"
    echo -e "${GREEN}  $HOME/.local/bin/babaam${NC}"
fi

echo ""
echo -e "${YELLOW}Kill them. Kill them all.${NC}"
echo ""
