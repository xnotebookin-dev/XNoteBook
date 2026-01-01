#!/bin/bash
# .platform/hooks/prebuild/01_install_tesseract.sh

# 1. Add the SPAL repository for AL2023 (contains Tesseract)
# This is the official way to get EPEL-like packages on AL2023
sudo dnf install -y https://github.com/stewartsmith/al2023-spal/releases/latest/download/spal-release.noarch.rpm

# 2. Install Tesseract and the English language pack
sudo dnf install -y tesseract tesseract-devel tesseract-langpack-eng

# 3. Ensure the binary is executable for the web user
sudo chmod +x /usr/bin/tesseract