#!/bin/bash

# Release script for Xbox Companion
# This script updates version numbers and creates a release zip

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}=== Xbox Companion Release Script ===${NC}"
echo ""

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    if [ -f package.json ] && command -v node >/dev/null 2>&1; then
        VERSION="$(node -p "require('./package.json').version")"
    fi
fi

if [ -z "$VERSION" ] && [ -t 0 ]; then
    read -p "Enter version number (e.g., 0.1.0-alpha.1): " VERSION
fi

if [ -z "$VERSION" ]; then
    echo -e "${RED}Error: No version provided and package.json version could not be read.${NC}"
    exit 1
fi

# Validate version format
if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    echo -e "${RED}Error: Invalid version format. Please use semantic versioning (e.g., 0.1.0-alpha.1)${NC}"
    exit 1
fi

echo ""
PACKAGE_VERSION="$(node -p "require('./package.json').version" 2>/dev/null || echo "$VERSION")"
if [ "$PACKAGE_VERSION" != "$VERSION" ]; then
    echo -e "${YELLOW}Packaging requested version ${VERSION}; package.json remains ${PACKAGE_VERSION}.${NC}"
fi

# Build the project
echo ""
echo -e "${YELLOW}Building project...${NC}"
pnpm run build
echo -e "${GREEN}✓ Build complete${NC}"

# Remove old release zips
rm -f xbox-companion-v*.zip

# Create release zip
ZIP_NAME="xbox-companion-v${VERSION}.zip"
echo ""
echo -e "${YELLOW}Creating release zip: ${ZIP_NAME}${NC}"
zip -r "$ZIP_NAME" dist main.py plugin.json package.json LICENSE README.md icons -x "*.DS_Store"
echo -e "${GREEN}✓ Release zip created${NC}"

# Show zip contents
echo ""
echo -e "${YELLOW}Zip contents:${NC}"
unzip -l "$ZIP_NAME"

echo ""
echo -e "${GREEN}=== Release v${VERSION} ready! ===${NC}"
echo -e "File: ${SCRIPT_DIR}/${ZIP_NAME}"
