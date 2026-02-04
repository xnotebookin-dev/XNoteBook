#!/bin/bash

# check if ffmpeg is already installed to save deployment time
if command -v ffmpeg &> /dev/null; then
    echo "ffmpeg is already installed. Skipping..."
    exit 0
fi

echo "Installing ffmpeg..."

# 1. Download the static build (usually the safest bet for AWS Linux)
cd /opt
sudo wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

# 2. Extract the archive
sudo tar -xf ffmpeg-release-amd64-static.tar.xz

# 3. Find the extracted folder name (it changes based on version)
FOLDER=$(find . -maxdepth 1 -type d -name "ffmpeg-*-amd64-static")

# 4. Move binaries to /usr/bin/ so they are in the global PATH
sudo cp "$FOLDER/ffmpeg" /usr/bin/
sudo cp "$FOLDER/ffprobe" /usr/bin/

# 5. Set permissions
sudo chmod +x /usr/bin/ffmpeg
sudo chmod +x /usr/bin/ffprobe

# 6. Cleanup
sudo rm -rf ffmpeg-release-amd64-static.tar.xz
sudo rm -rf "$FOLDER"

echo "ffmpeg installation complete."