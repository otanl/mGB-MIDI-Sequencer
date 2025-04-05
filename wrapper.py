#!/usr/bin/env python
import os
import sys
import time
import logging
import tkinter as tk
import threading
import subprocess
import webbrowser
import platform
import traceback
import http.server
import socketserver
import socket

def setup_logging():
    """ロギングのセットアップ"""
    # アプリケーションディレクトリを取得
    if getattr(sys, 'frozen', False):
        # EXE実行時のパス
        base_dir = os.path.dirname(sys.executable)
    else:
        # 通常実行時のパス
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    log_file = os.path.join(base_dir, "app_log.txt")
    
    # ファイルにBOMを追加（UTF-8エンコーディングのマーカー）
    try:
        with open(log_file, 'wb') as f:
            # UTF-8 BOMを追加
            f.write(b'\xef\xbb\xbf')
    except Exception:
        pass
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8-sig'),
            logging.StreamHandler()
        ]
    )
    
    # システム情報をログに出力
    logging.info(f"アプリケーションディレクトリ: {base_dir}")
    logging.info(f"Python バージョン: {sys.version}")
    logging.info(f"実行ファイル: {sys.executable}")
    logging.info(f"実行モード: {'凍結実行ファイル' if getattr(sys, 'frozen', False) else '通常Python'}")
    logging.info(f"システム環境変数:")
    for key, value in os.environ.items():
        if key in ['PYTHONPATH', 'PATH', 'SYSTEMROOT', 'USERPROFILE']:
            logging.info(f"  {key}: {value}")

def get_resources_path():
    """リソースディレクトリのパスを取得"""
    # 実行ファイルのディレクトリを基準にする
    if getattr(sys, 'frozen', False):
        # EXE実行時のパス
        base_dir = os.path.dirname(sys.executable)
    else:
        # 通常実行時のパス
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # リソースディレクトリのパス
    resource_path = os.path.join(base_dir, "resources")
    
    # リソースディレクトリが存在しない場合は作成
    if not os.path.exists(resource_path):
        os.makedirs(resource_path)
        logging.info(f"リソースディレクトリを作成しました: {resource_path}")
    
    return resource_path

def get_local_ip():
    """ローカルIPアドレスを取得"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        logging.error(f"IPアドレス取得エラー: {e}")
        return "localhost"

# HTTPサーバーの設定
class SimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # ログメッセージをカスタマイズ
        logging.info(f"HTTP: {self.address_string()} - {format % args}")

def start_http_server(resource_path, port=8000):
    """HTTPサーバーを起動"""
    try:
        # 現在のディレクトリを保存
        original_dir = os.getcwd()
        
        # リソースディレクトリに移動
        os.chdir(resource_path)
        
        # サーバーポートが使用中の場合は別のポートを試す
        for attempt_port in range(port, port + 10):
            try:
                handler = SimpleHTTPRequestHandler
                httpd = socketserver.TCPServer(("", attempt_port), handler)
                port = attempt_port
                break
            except OSError:
                logging.warning(f"ポート {attempt_port} は使用中です。次のポートを試します...")
                continue
        else:
            logging.error("利用可能なポートが見つかりませんでした")
            os.chdir(original_dir)
            return None, port
        
        logging.info(f"HTTPサーバーを開始: http://localhost:{port}")
        logging.info(f"ローカルIP: http://{get_local_ip()}:{port}")
        
        # サーバーを別スレッドで起動
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # 元のディレクトリに戻る
        os.chdir(original_dir)
        
        return httpd, port
    except Exception as e:
        logging.error(f"HTTPサーバー起動エラー: {e}")
        traceback.print_exc()
        return None, port

def open_browser(resource_path, port=8000):
    """ブラウザでHTMLクライアントを開く"""
    try:
        # 待機時間を短縮
        time.sleep(1)
        
        # ローカルIPを取得
        ip = get_local_ip()
        
        # HTMLファイルのパス
        html_path = os.path.join(resource_path, "midi_sequencer_client.html")
        
        if os.path.exists(html_path):
            # WebSocketのURLパラメータを追加
            url = f"http://localhost:{port}/midi_sequencer_client.html?wsurl=ws://{ip}:8765"
            logging.info(f"ブラウザを開きます: {url}")
            
            # 標準的な方法でブラウザを開く
            if not webbrowser.open(url):
                logging.warning("標準的なブラウザの起動に失敗しました。代替方法を試みます...")
                
                # 代替方法: OS固有のコマンドを使用
                try:
                    if platform.system() == "Windows":
                        os.system(f'start "" "{url}"')
                    elif platform.system() == "Darwin":  # macOS
                        os.system(f'open "{url}"')
                    elif platform.system() == "Linux":
                        os.system(f'xdg-open "{url}"')
                    logging.info("代替方法でブラウザを開きました")
                except Exception as e:
                    logging.error(f"代替ブラウザ起動エラー: {e}")
                    # 最終手段: ファイルURLを試す
                    file_url = f"file://{os.path.abspath(html_path)}"
                    logging.info(f"ファイルURLを試みます: {file_url}")
                    webbrowser.open(file_url)
        else:
            logging.error(f"HTMLファイルが見つかりません: {html_path}")
            return False
            
        return True
    except Exception as e:
        logging.error(f"ブラウザ起動エラー: {e}")
        return False

def run_midi_sequencer():
    """MIDIシーケンサーを実行"""
    try:
        # モジュールパスを追加（EXE実行時のための対応）
        if getattr(sys, 'frozen', False):
            module_dir = os.path.dirname(sys.executable)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)
                logging.info(f"モジュールパスを追加: {module_dir}")
        
        # MIDIシーケンサーモジュールをインポート
        try:
            import midi_sequencer_api
            import midi_sequencer_mgb
            logging.info("MIDIシーケンサーモジュールを読み込みました")
        except ImportError as e:
            logging.error(f"モジュールのインポートに失敗しました: {e}")
            # インポートパスを表示
            logging.info(f"sys.path: {sys.path}")
            raise
        
        # リソースパスを取得
        resource_path = get_resources_path()
        logging.info(f"リソースパス: {resource_path}")
        
        # HTMLクライアントの確認
        html_path = os.path.join(resource_path, "midi_sequencer_client.html")
        if not os.path.exists(html_path):
            # カレントディレクトリにHTMLクライアントがある場合はコピー
            current_html = os.path.join(os.getcwd(), "midi_sequencer_client.html")
            if os.path.exists(current_html):
                import shutil
                shutil.copy2(current_html, html_path)
                logging.info(f"HTMLクライアントをコピーしました: {current_html} -> {html_path}")
            else:
                logging.error(f"HTMLクライアントが見つかりません: {html_path}")
                logging.error(f"カレントディレクトリにも見つかりません: {current_html}")
                return 1
        
        # HTTPサーバーを起動
        httpd, http_port = start_http_server(resource_path)
        
        if not httpd:
            logging.error("HTTPサーバーの起動に失敗しました")
            return 1
        
        # サーバーポート情報
        websocket_port = 8765
        
        # tkinterのルートウィンドウを作成
        root = tk.Tk()
        root.title("mGB MIDI Sequencer")
        
        # MIDIシーケンサーのインスタンスを作成
        sequencer = midi_sequencer_mgb.MidiSequencer(root)
        
        # WebSocketサーバーを起動
        try:
            # 外部からアクセスできるように0.0.0.0に設定
            server = midi_sequencer_api.run_websocket_server(sequencer, websocket_port, host='0.0.0.0')
            
            # サーバー情報をログに出力
            ip = get_local_ip()
            logging.info(f"WebSocketサーバー: ws://{ip}:{websocket_port}")
            logging.info(f"HTTP: http://{ip}:{http_port}")
            
            # ブラウザを開く
            open_browser(resource_path, http_port)
        except Exception as e:
            logging.error(f"WebSocketサーバー起動エラー: {e}")
            traceback.print_exc()
            return 1
        
        # アプリケーション終了時の処理
        def on_closing():
            try:
                logging.info("アプリケーションを終了します")
                logging.info("--------------------------------------------------")
                # サーバーを停止
                if 'server' in locals() and server:
                    server.stop()
                # HTTPサーバーを停止
                if 'httpd' in locals() and httpd:
                    httpd.shutdown()
                # アクティブなスレッドを終了
                for t in threading.enumerate():
                    if t != threading.main_thread():
                        logging.info(f"スレッド終了待機中: {t.name}")
                # ウィンドウを破棄
                root.destroy()
                
                logging.info(f"Application end time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                sys.exit(0)
            except Exception as e:
                logging.error(f"終了時エラー: {e}")
                sys.exit(1)
        
        # ウィンドウ終了イベントをハンドリング
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # メインループを開始（Tkinterのウィンドウを表示）
        root.mainloop()
        
        logging.info("tkinter メインループが終了しました")
        
    except Exception as e:
        logging.error(f"実行時エラー: {e}")
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    # ログ設定
    setup_logging()
    logging.info(f"Starting application: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # シーケンサーを実行
    sys.exit(run_midi_sequencer())
