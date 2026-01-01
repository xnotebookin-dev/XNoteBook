#!/bin/bash

# 1. Install EPEL 9 repository (contains Tesseract for AL2023)
sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

# 2. Force install Tesseract and the English language pack
sudo dnf install -y tesseract tesseract-devel tesseract-langpack-eng --nogpgcheck

# 3. Ensure permissions are correct for the web user
sudo chmod +x /usr/bin/tesseract