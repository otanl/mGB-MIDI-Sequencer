#!/bin/bash
echo "mGB MIDI Sequencer のセットアップを開始します..."

# Pythonがインストールされているか確認
if ! command -v python3 &> /dev/null; then
    echo "Pythonがインストールされていません。Pythonをインストールしてから再実行してください。"
    exit 1
fi

# 仮想環境の存在確認と作成
if [ ! -d "venv" ]; then
    echo "仮想環境を作成しています..."
    python3 -m venv venv
fi

# 仮想環境を有効化して依存パッケージをインストール
echo "必要なパッケージをインストールしています..."
source venv/bin/activate
if ! python3 -m pip install -r requirements.txt; then
    echo "パッケージのインストールに失敗しました。"
    echo "requirements.txtが正しいフォーマットであることを確認してください。"
    deactivate
    exit 1
fi

echo "mGB MIDI Sequencer を起動中..."
python3 wrapper.py

# 仮想環境を無効化
deactivate 