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

REM requirements.txtを一時的に作成してUTF-8で保存
echo # MIDIシーケンサーの依存関係 > requirements_temp.txt
echo mido^>=1.2.10 >> requirements_temp.txt
echo python-rtmidi^>=1.4.9 >> requirements_temp.txt
echo websockets^>=10.3 >> requirements_temp.txt

python -m pip install -r requirements_temp.txt
if errorlevel 1 (
    echo パッケージのインストールに失敗しました。
    echo requirements.txtのフォーマットに問題がある可能性があります。
    del requirements_temp.txt
    call venv\Scripts\deactivate.bat
    pause
    exit /b
)

REM 一時ファイルを削除
del requirements_temp.txt

echo mGB MIDI Sequencer を起動中...
python wrapper.py

REM 仮想環境を無効化
call venv\Scripts\deactivate.bat
pause 