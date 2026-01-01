#!/bin/bash
# .platform/hooks/prebuild/01_install_tesseract.sh

# 1. Create a repository entry for the Fedora 36 Archive
# We use the archive because these URLs are permanent and will not return 404.
cat <<EOF | sudo tee /etc/yum.repos.d/fedora-archive.repo
[fedora-archive]
name=Fedora 36 Archive
baseurl=https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/36/Everything/\$basearch/os/
enabled=1
gpgcheck=0
skip_if_unavailable=False
EOF

# 2. Install Tesseract and dependencies from this new repo
# The 'clean all' ensures dnf sees the new repo immediately.
sudo dnf clean all
sudo dnf install -y tesseract tesseract-devel tesseract-langpack-eng

# 3. Ensure the binary is executable
sudo chmod +x /usr/bin/tesseract