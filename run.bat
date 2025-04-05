@echo off
chcp 65001 > nul
echo mGB MIDI Sequencer のセットアップを開始します...

REM Pythonがインストールされているか確認
python --version 2>nul
if errorlevel 1 (
    echo Pythonがインストールされていません。Pythonをインストールしてから再実行してください。
    pause
    exit /b
)

REM 仮想環境の存在確認と作成
if not exist "venv" (
    echo 仮想環境を作成しています...
    python -m venv venv
)

REM 仮想環境を有効化して依存パッケージをインストール
echo 必要なパッケージをインストールしています...
call venv\Scripts\activate
python -m pip install -r requirements.txt

echo mGB MIDI Sequencer を起動中...
python wrapper.py

REM 仮想環境を無効化
call venv\Scripts\deactivate.bat
pause 