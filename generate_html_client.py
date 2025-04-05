#!/usr/bin/env python
# -*- coding: utf-8 -*-
import socket
import re
import os

def get_local_ip():
    """ローカルIPアドレスを取得する"""
    try:
        # 外部接続用のソケットを作成
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 外部接続を確立（実際には接続されません）
        s.connect(("8.8.8.8", 80))
        # 自身のIPアドレスを取得
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # エラーの場合はループバックアドレスを返す
        return "127.0.0.1"

def generate_html_client():
    # ローカルIPアドレスを取得
    local_ip = get_local_ip()
    
    # テンプレートファイル名
    template_file = "midi_sequencer_template.html"
    output_file = "midi_sequencer_client.html"
    
    # テンプレートファイルが存在しない場合は出力ファイルをテンプレートとして使用
    if not os.path.exists(template_file) and os.path.exists(output_file):
        template_file = output_file
    
    # ファイルが存在しない場合は基本的なテンプレートを作成
    if not os.path.exists(template_file):
        with open(template_file, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>mGB MIDIシーケンサーコントローラー</title>
    <!-- スタイルとコンテンツが入ります -->
</head>
<body>
    <h1>mGB MIDIシーケンサーコントローラー</h1>
    
    <div class="connection-status disconnected" id="connectionStatus">切断</div>
    
    <script>
        // WebSocket接続
        const wsUrl = 'ws://localhost:8765';
        // その他のJavaScriptコード
    </script>
</body>
</html>""")
    
    # テンプレートファイルを読み込む
    with open(template_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # WebSocketのURLを置換
    ws_url_pattern = r"const wsUrl = ['\"]ws://[^:]+:8765['\"];"
    ws_url_replacement = f"const wsUrl = 'ws://{local_ip}:8765';"
    
    # 再接続ロジックを改善（最大試行回数を設定）
    pattern_reconnect = r"reconnectInterval = setInterval\(connectWebSocket, 3000\);"
    replacement_reconnect = """
                        // 再接続試行回数を制限
                        let reconnectAttempts = 0;
                        const maxReconnectAttempts = 3;
                        reconnectInterval = setInterval(() => {
                            if (reconnectAttempts < maxReconnectAttempts) {
                                reconnectAttempts++;
                                console.log(`再接続を試みます (${reconnectAttempts}/${maxReconnectAttempts})...`);
                                connectWebSocket();
                            } else {
                                console.log('最大再接続試行回数に達しました。手動での再接続が必要です。');
                                clearInterval(reconnectInterval);
                                reconnectInterval = null;
                                
                                // 手動再接続ボタンを追加
                                const reconnectButton = document.createElement('button');
                                reconnectButton.textContent = 'サーバーに再接続';
                                reconnectButton.onclick = () => {
                                    reconnectAttempts = 0;
                                    connectWebSocket();
                                };
                                statusElement.appendChild(reconnectButton);
                            }
                        }, 3000);"""
    
    updated_content = re.sub(ws_url_pattern, ws_url_replacement, content)
    updated_content = re.sub(pattern_reconnect, replacement_reconnect, updated_content)
    
    # 更新したコンテンツを保存
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(updated_content)
    
    print(f"HTMLクライアントを生成しました: {output_file} (WebSocket URL: ws://{local_ip}:8765)")

if __name__ == "__main__":
    generate_html_client() 