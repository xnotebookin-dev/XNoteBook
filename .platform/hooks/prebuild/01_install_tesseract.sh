#!/bin/bash
# .platform/hooks/prebuild/01_install_tesseract.sh

# Directly install Tesseract and English langpack
sudo dnf install -y https://dl.fedoraproject.org/pub/fedora/linux/releases/39/Everything/x86_64/os/Packages/t/tesseract-5.3.3-2.fc39.x86_64.rpm \
https://dl.fedoraproject.org/pub/fedora/linux/releases/39/Everything/x86_64/os/Packages/t/tesseract-langpack-eng-5.3.3-2.fc39.noarch.rpm --nogpgcheck

# Explicitly grant execution permissions to the binary for the web user
sudo chmod +x /usr/bin/tesseract