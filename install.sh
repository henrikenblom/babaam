#!/usr/bin/env bash

# BA-BAAM! Installation Script
# This script can be run either:
# 1. Locally after cloning the repository
# 2. Remotely via: curl -s https://raw.githubusercontent.com/henrikenblom/babaam/master/install.sh | bash

set -e  # Exit on error

# Determine if we're running locally or remotely
if [ -f "$(dirname "${BASH_SOURCE[0]}")/babaam.py" ]; then
    # Running locally from cloned repo
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    LOCAL_INSTALL=true
else
    # Running remotely, delegate to remote-install.sh
    echo "Detected remote execution, downloading remote installer..."
    curl -s https://raw.githubusercontent.com/henrikenblom/babaam/master/remote-install.sh | bash
    exit $?
fi

GAME_NAME="BA-BAAM!"
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

# Create installation directory
echo -e "${YELLOW}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv" || {
        echo -e "${RED}ERROR: Failed to create virtual environment.${NC}"
        exit 1
    }
fi

# Install Python dependencies in virtual environment
echo -e "${YELLOW}Installing Python dependencies...${NC}"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install pynput pygame numpy || {
    echo -e "${RED}ERROR: Failed to install Python dependencies.${NC}"
    echo "You can try installing manually with:"
    echo "  $INSTALL_DIR/venv/bin/pip install pynput pygame numpy"
    exit 1
}
echo -e "${GREEN}Python dependencies installed successfully!${NC}"

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

# Check if virtual environment exists
if [ ! -f "$INSTALL_DIR/venv/bin/python3" ]; then
    echo "ERROR: Virtual environment is missing."
    echo "Please run install.sh again."
    exit 1
fi

# Run the game using virtual environment Python
cd "$INSTALL_DIR"
exec "$INSTALL_DIR/venv/bin/python3" "$INSTALL_DIR/babaam.py"
LAUNCHER_EOF

chmod +x "$BIN_DIR/babaam"

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

    # Check if PATH is already configured in rc file
    if grep -q "# Added by BA-BAAM! installer" "$RC_FILE" 2>/dev/null; then
        echo -e "${YELLOW}PATH configuration already exists in ${RC_FILE}${NC}"
        PATH_CONFIGURED=false
        PATH_ALREADY_IN_RC=true
    else
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
            PATH_CONFIGURED=false
            PATH_JUST_ADDED=true
        else
            echo -e "${YELLOW}Skipping PATH configuration.${NC}"
            PATH_CONFIGURED=false
            PATH_JUST_ADDED=false
        fi
        PATH_ALREADY_IN_RC=false
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

# Show prominent restart reminder if PATH was added or already exists in rc file
if [ "${PATH_ALREADY_IN_RC:-false}" = true ] || [ "${PATH_JUST_ADDED:-false}" = true ]; then
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                          IMPORTANT NOTICE                             ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}The PATH configuration is in your ${RC_FILE}, but it's NOT active${NC}"
    echo -e "${YELLOW}in this terminal session yet.${NC}"
    echo ""
    echo -e "${YELLOW}To activate it, you MUST do ONE of the following:${NC}"
    echo -e "${GREEN}  1. Restart your terminal (close and reopen)${NC}"
    echo -e "${GREEN}  2. Open a new terminal window${NC}"
    echo -e "${GREEN}  3. Run: source ${RC_FILE}${NC}"
    echo ""
    echo -e "${YELLOW}After that, you can use the 'babaam' command directly.${NC}"
    echo ""
fi
