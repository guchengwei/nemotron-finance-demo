#!/usr/bin/env bash
set -euo pipefail

# Install MeCab system library (required for fugashi Japanese tokenizer)
if [[ "$(uname)" == "Linux" ]]; then
  sudo apt-get update && sudo apt-get install -y mecab libmecab-dev
elif [[ "$(uname)" == "Darwin" ]]; then
  brew install mecab
fi

# Install Python dependencies
pip install -r requirements.txt
