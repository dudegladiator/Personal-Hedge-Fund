#!/bin/bash

if [ "$(uname -s)" == "Linux" ]; then
    tar -xzf ta-lib-0.6.4-src.tar.gz
    cd ta-lib-0.6.4
    ./configure --prefix=/usr
    make
    sudo make install
    cd ..
else
    echo "Unsupported operating system or manual installation required for Windows. Please follow README instructions."
    exit 1
fi

uv add -r requirements.txt