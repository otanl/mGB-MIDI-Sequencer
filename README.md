# mGB MIDI Sequencer



## 概要

mGB MIDI Sequencerは、ゲームボーイ用のMIDIシーケンサーアプリケーションです。Arduinoboyを介してmGBを操作、またはMIDIルーティングを通じてRetroPlugをコントロール可能です。
また、APIを提供しており、mGB-MCP ([GitHub: mGB-MCP](https://github.com/otanl/mGB-MCP))と連携して使用することを前提としています。

主な特徴：
- 5トラックのシーケンサー（PU1、PU2、WAV、NOISE、POLY）
- 16ステップシーケンス
- 2連符、3連符などのノート分割設定
- パルス幅やエンベロープなどのCCパラメータコントロール
- WebSocket APIによるリモートコントロール
- HTMLクライアントによるブラウザベースのインターフェース
- MIDIクロック同期

## インストール方法

### 必要条件
- Python 3.7以上
- 以下のPythonパッケージ:
  - mido
  - python-rtmidi
  - websockets
  - asyncio
- MIDI対応のGameBoyインターフェース（Arduinoboy、midiboy等）

### インストール手順

1. ZIPファイルをダウンロードして任意の場所に解凍します。

2. 必要なパッケージをインストールします：
```
pip install -r requirements.txt
```

## 使用方法

### アプリケーションの実行

推奨される起動方法:

- **Windows**:
  ```
  run.bat
  ```

- **Mac/Linux**:
  ```
  ./run.sh
  ```

または、Pythonから直接実行する場合:
```
python wrapper.py
```

これによりWebSocketサーバーが起動し、シーケンサーUIとHTMLクライアントが開きます。

### 基本的な操作

1. **シーケンスの作成**：
   - 各ステップをクリックしてオン/オフを切り替えます
   - Shift+クリックでノート設定ダイアログを開きます
   - ノート値と分割設定（1、2連符、3連符）を設定できます

2. **再生コントロール**：
   - 再生/停止ボタンでシーケンスを開始/停止します
   - BPM値を変更してテンポを調整します

3. **MIDI設定**：
   - MIDI出力デバイスを選択します（Arduinoboyなど）
   - MIDIクロック同期を有効/無効にできます

4. **パラメータ調整**：
   - CCスライダーでパルス幅、エンベロープなどを調整できます
   - 各トラックごとに異なるパラメータを設定できます

### ノート分割設定

各ステップには「分割設定」があり、通常の再生（1）、2連符（2）、3連符（3）から選択できます：

- **1（通常）**：標準的な再生間隔
- **2（2連符）**：1ステップを2つに分割
- **3（3連符）**：1ステップを3つに分割

## WebSocket API

mGB MIDI シーケンサーはWebSocket APIを提供し、外部アプリケーションからの制御が可能です。

詳細な API ドキュメントは [api_documentation.md](api_documentation.md) を参照してください。

### WebSocket接続

```
ws://localhost:8765
```

### 基本的なコマンド例

```javascript
// 再生/停止の切り替え
ws.send(JSON.stringify({
  command: 'toggle_play'
}));

// BPMの設定
ws.send(JSON.stringify({
  command: 'set_bpm',
  bpm: 120
}));

// ノート設定
ws.send(JSON.stringify({
  command: 'set_note',
  row: 0,
  col: 4,
  note: 60,
  divide: 2  // 2連符
}));

// CCパラメータの更新
ws.send(JSON.stringify({
  command: 'update_cc',
  track: 'PU1',
  cc: 'cc1',
  value: 64
}));
```

## HTMLクライアント

アプリケーション起動時に自動的にHTMLクライアントがブラウザで開きます。このクライアントを使用すると、ブラウザ上でシーケンサーを制御できます。

別のデバイスからアクセスする場合は、以下のURLを使用します：
```
http://<サーバーのIPアドレス>:8000/midi_sequencer_client.html
```

## トラブルシューティング

1. **MIDIデバイスが見つからない場合**：
   - MIDIデバイスが接続されていることを確認してください
   - ドライバが正しくインストールされていることを確認してください

2. **WebSocket接続エラー**：
   - サーバーが実行されていることを確認してください
   - ファイアウォールの設定を確認してください

3. **パラメータ変更が効かない場合**：
   - api_documentation.mdの指示に従って正確なパラメータ名と値を使用してください
   - CC値の範囲（0～127）を超えていないか確認してください

4. **HTML/ブラウザUIが開かない場合**：
   - 手動でブラウザを開き、`http://localhost:8000/midi_sequencer_client.html` にアクセスしてください
   - ブラウザのコンソールでエラーがないか確認してください

## ライセンス

MIT License

## 謝辞

このプロジェクトは [Arduinoboy](https://github.com/trash80/Arduinoboy) および [mGB](https://github.com/trash80/mGB) 、 [RetroPlug](https://github.com/tommitytom/RetroPlug) と連携して動作します。オリジナルの開発者に感謝いたします。

