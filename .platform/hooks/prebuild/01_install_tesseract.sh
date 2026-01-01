#!/bin/bash
# .platform/hooks/prebuild/01_install_tesseract.sh

# 1. Add the SPAL repository for AL2023 (contains Tesseract)
# This bypasses the EPEL dependency error.
sudo dnf install -y https://github.com/stewartsmith/al2023-spal/releases/latest/download/spal-release.noarch.rpm

# 2. Install Tesseract and the English language pack
sudo dnf install -y tesseract tesseract-devel tesseract-langpack-eng

# 3. Ensure the binary is executable
sudo chmod +x /usr/bin/tesseract