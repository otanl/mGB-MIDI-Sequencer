import asyncio
import json
import websockets
import tkinter as tk
from midi_sequencer_mgb import MidiSequencer
import time
from generate_html_client import generate_html_client
import threading
import http.server
import socketserver
import webbrowser
import os
import socket
import mido

def create_midi_sequencer():
    """MidiSequencerのインスタンスを作成して返す"""
    root = tk.Tk()
    sequencer = MidiSequencer(root)
    return sequencer

def run_websocket_server(sequencer, port=8765, host='0.0.0.0'):
    """WebSocketサーバーを起動する"""
    # WebSocketサーバーを作成
    server = WebSocketServer(sequencer, host=host, port=port)
    
    # シーケンサーにWebSocketサーバーへの参照を設定
    sequencer.websocket_server = server
    
    # サーバーを起動
    server.start()
    
    return server

def get_midi_ports():
    """利用可能なMIDIポートを取得する"""
    try:
        output_ports = mido.get_output_names()
        input_ports = mido.get_input_names()
        
        # 長いリストの場合、表示を整形
        if output_ports:
            output_msg = 'MIDI出力ポート:\n' + '\n'.join([f'  - {i}: {port}' for i, port in enumerate(output_ports)])
            print(output_msg)
        else:
            print("MIDI出力ポートが見つかりません")
            
        if input_ports:
            input_msg = 'MIDI入力ポート:\n' + '\n'.join([f'  - {i}: {port}' for i, port in enumerate(input_ports)])
            print(input_msg)
        else:
            print("MIDI入力ポートが見つかりません")
        
        return output_ports, input_ports
    except Exception as e:
        print(f"MIDIポート取得エラー: {e}")
        return [], []

def get_local_ip():
    """ローカルIPアドレスを取得する"""
    try:
        # ホスト名を取得
        hostname = socket.gethostname()
        # IPアドレスを取得
        local_ip = socket.gethostbyname(hostname)
        print(f"ホスト名: {hostname}, IPアドレス: {local_ip}")
        return local_ip
    except Exception as e:
        print(f"ローカルIPアドレス取得エラー: {e}")
        return "localhost"

class WebSocketServer:
    def __init__(self, sequencer, host='0.0.0.0', port=8765):
        self.sequencer = sequencer
        self.host = host
        self.port = port
        self.clients = set()
        self.client_info = {}  # クライアント情報を保持
        self.server = None
        self.is_running = False
        self.state_update_task = None
        self.state_update_interval = 0.03  # 30msに短縮（元は0.1s）
        self.last_state_update = 0
        self.max_clients = 5  # 最大クライアント数
    
    async def register(self, websocket):
        """クライアント接続を登録する"""
        # クライアント数が上限に達している場合
        if len(self.clients) >= self.max_clients:
            print(f"最大クライアント数({self.max_clients})に達しています。新しい接続を拒否します。")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'サーバーは最大接続数({self.max_clients})に達しています。後でやり直してください。'
            }))
            # 接続を閉じる
            await websocket.close(code=1000, reason="Maximum clients reached")
            return
        
        # クライアントの接続元情報を取得
        try:
            client_ip = websocket.remote_address[0] if websocket.remote_address else 'unknown'
            
            # 一時的なクライアントIDを作成 - 実際のクライアントIDはメッセージで後から送信される
            temp_client_id = f"{client_ip}:{int(time.time())}"
            
            # 新しいクライアント情報を登録
            self.client_info[websocket] = {
                'id': temp_client_id,
                'ip': client_ip,
                'connected_at': time.time(),
                'verified': False  # クライアントIDが正式に検証されていない
            }
        except Exception as e:
            print(f"クライアント情報の取得中にエラーが発生しました: {e}")
            try:
                await websocket.close(code=1011, reason="Failed to register client")
            except:
                pass
            return
        
        # クライアントを登録
        self.clients.add(websocket)
        print(f"クライアント接続: 現在{len(self.clients)}接続")
        
        # 現在の状態を送信
        await self.send_state(websocket)
        
        # 状態更新タスクが実行されていない場合は開始
        if self.state_update_task is None:
            self.state_update_task = asyncio.create_task(self.periodic_state_update())
    
    async def unregister(self, websocket):
        """クライアント接続を解除する"""
        if websocket in self.clients:
            self.clients.remove(websocket)
            
            # クライアント情報もクリア
            if websocket in self.client_info:
                del self.client_info[websocket]
                
            print(f"クライアント切断: 残り{len(self.clients)}接続")
            
            # クライアントが0になったら状態更新タスクを停止
            if len(self.clients) == 0 and self.state_update_task:
                self.state_update_task.cancel()
                self.state_update_task = None
    
    async def send_state(self, websocket=None):
        """現在のシーケンサーの状態を送信する"""
        try:
            # 接続クライアントがない場合は何もしない
            if not self.clients and websocket is None:
                print("接続中のクライアントはありません。状態を送信しませんでした。")
                return

            # note_cc_valuesが未初期化の場合は初期化
            if not hasattr(self.sequencer, 'note_cc_values'):
                self.sequencer.note_cc_values = {}

            # 利用可能なMIDIポートを取得
            available_midi_outputs = []
            available_midi_inputs = []
            try:
                available_midi_outputs = mido.get_output_names()
                available_midi_inputs = mido.get_input_names()
                print(f"利用可能なMIDI出力ポート: {available_midi_outputs}")
                print(f"利用可能なMIDI入力ポート: {available_midi_inputs}")
            except Exception as e:
                print(f"MIDIポートの取得中にエラーが発生しました: {e}")
                import traceback
                traceback.print_exc()
                # エラーが発生しても既存のポートリストがあれば使用する
                try:
                    if hasattr(self.sequencer, 'available_ports'):
                        available_midi_outputs = self.sequencer.available_ports
                    if hasattr(self.sequencer, 'available_input_ports'):
                        available_midi_inputs = self.sequencer.available_input_ports
                    print(f"既存のポートリストを使用: 出力={available_midi_outputs}, 入力={available_midi_inputs}")
                except Exception as e2:
                    print(f"既存ポートリスト取得エラー: {e2}")

            # 状態のデータを構築
            state = {
                'type': 'state',
                'sequence': self.sequencer.sequence,
                'note_values': self.sequencer.note_values,
                'note_divides': self.sequencer.note_divides,
                'cc_values': self.sequencer.cc_values,
                'current_step': self.sequencer.current_step,
                'is_playing': self.sequencer.is_playing,
                'bpm': self.sequencer.bpm,
                'available_midi_outputs': available_midi_outputs,
                'available_midi_inputs': available_midi_inputs,
                'midi_output': self.sequencer.port_name,
                'midi_input': self.sequencer.input_port_name,
                'midi_clock_enabled': self.sequencer.midi_clock_enabled,
                'note_cc_values': self.sequencer.note_cc_values,
                'clock_divide': self.sequencer.clock_divide if hasattr(self.sequencer, 'clock_divide') else 1
            }

            state_json = json.dumps(state)
            
            # デバッグ情報：状態データの詳細をログに出力
            print(f"状態データに含まれる項目: {', '.join(state.keys())}")
            print(f"MIDIポート情報: 出力={len(available_midi_outputs)}個, 入力={len(available_midi_inputs)}個")
            print(f"note_divides配列のサイズ: {len(self.sequencer.note_divides)}行 x {len(self.sequencer.note_divides[0]) if self.sequencer.note_divides else 0}列")
            
            # 特定のクライアントのみに送信する場合
            if websocket:
                print(f"特定クライアントに状態データを送信: {len(state_json)}バイト, クライアントID: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                await websocket.send(state_json)
                return
                
            # すべてのクライアントに状態を送信
            print(f"すべてのクライアントに状態メッセージを送信します: {len(state_json)}バイト")
            for client in self.clients:
                try:
                    await client.send(state_json)
                except Exception as e:
                    print(f"クライアントへの状態送信中にエラーが発生: {e}")
        except Exception as e:
            print(f"状態データ送信エラー: {e}")
            import traceback
            traceback.print_exc()
    
    async def handle_message(self, websocket, message):
        """クライアントからのメッセージを処理する"""
        try:
            data = json.loads(message)
            command = data.get('command')
            
            # クライアントIDの処理
            client_id = data.get('client_id')
            if client_id and websocket in self.client_info:
                client_info = self.client_info[websocket]
                if not client_info.get('verified'):
                    # クライアントIDが初めて送信された場合
                    client_ip = client_info.get('ip', 'unknown')
                    print(f"クライアントID受信: {client_id} (IP: {client_ip})")
                    
                    # 同じIPアドレスからの既存の検証済み接続を確認
                    duplicate_connection = False
                    for ws in list(self.clients):
                        if ws != websocket and ws in self.client_info:
                            ws_info = self.client_info[ws]
                            if ws_info.get('ip') == client_ip and ws_info.get('verified') and ws_info.get('id').endswith(client_id):
                                # 既に同じIPからのアクティブな接続があり、同じクライアントIDを持つ場合
                                try:
                                    # pingを送信して接続状態を確認
                                    pong_waiter = await ws.ping()
                                    await asyncio.wait_for(pong_waiter, timeout=1.0)
                                    # 既存の接続が生きている場合、重複とマーク
                                    duplicate_connection = True
                                    print(f"同一クライアント({client_id})からの重複接続を検出")
                                    # 最も新しい接続を維持
                                    if ws_info.get('connected_at', 0) < client_info.get('connected_at', 0):
                                        # 既存の接続のほうが古い場合は既存を閉じる
                                        print(f"古い接続を閉じます: {ws_info.get('id')}")
                                        await ws.close(code=1000, reason="Newer connection established")
                                        self.clients.remove(ws)
                                        del self.client_info[ws]
                                        duplicate_connection = False
                                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                                    # 接続が失われている場合は無視
                                    self.clients.remove(ws)
                                    del self.client_info[ws]
                                    duplicate_connection = False
                    
                    if duplicate_connection:
                        # 重複接続の場合、このクライアントを閉じる
                        print(f"重複接続を閉じます: {client_id}")
                        await websocket.send(json.dumps({
                            'type': 'error',
                            'message': '別のブラウザで既に接続が確立されています。'
                        }))
                        await websocket.close(code=1000, reason="Duplicate connection")
                        if websocket in self.clients:
                            self.clients.remove(websocket)
                        if websocket in self.client_info:
                            del self.client_info[websocket]
                        return
                    
                    # クライアントIDを更新し、検証済みとマーク
                    client_info['id'] = f"{client_ip}:{client_id}"
                    client_info['verified'] = True
                    print(f"クライアント検証完了: {client_info['id']}")
            
            # コマンド処理
            if command == 'get_state':
                await self.send_state(websocket)
            
            elif command == 'get_current_state':
                current_state = {
                    'type': 'current_state',
                    'sequence': self.sequencer.sequence,
                    'note_values': self.sequencer.note_values,
                    'cc_values': self.sequencer.cc_values,
                    'current_step': self.sequencer.current_step,
                    'is_playing': self.sequencer.is_playing,
                    'bpm': self.sequencer.bpm
                }
                await websocket.send(json.dumps(current_state))
            
            elif command == 'batch_update':
                updates = data.get('updates', [])
                for update in updates:
                    update_type = update.get('type')
                    
                    if update_type == 'sequence':
                        row = update.get('row')
                        col = update.get('col')
                        state = update.get('state')
                        if row is not None and col is not None and state is not None:
                            self.sequencer.sequence[int(row)][int(col)] = state
                            if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][int(col)]:
                                button = self.sequencer.step_buttons[int(row)][int(col)]
                                button_color = self.sequencer.active_color if state else self.sequencer.inactive_color
                                button.config(bg=button_color)
                    
                    elif update_type == 'note':
                        row = update.get('row')
                        col = update.get('col')
                        note = update.get('note')
                        if row is not None and col is not None and note is not None:
                            self.sequencer.note_values[int(row)][int(col)] = note
                            if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][int(col)]:
                                self.sequencer.update_button_text(int(row), int(col), self.sequencer.step_buttons[int(row)][int(col)])
                                if hasattr(self.sequencer, 'note_labels') and self.sequencer.note_labels[int(row)][int(col)]:
                                    note_name = self.sequencer.get_note_name(int(note))
                                    self.sequencer.note_labels[int(row)][int(col)].config(text=note_name)
                    
                    elif update_type == 'note_cc':
                        # ノートごとのCC値処理
                        row = update.get('row')
                        col = update.get('col')
                        cc = update.get('cc')
                        value = update.get('value')
                        
                        if row is not None and col is not None and cc and value is not None:
                            # note_cc_valuesが未初期化の場合は初期化
                            if not hasattr(self.sequencer, 'note_cc_values'):
                                self.sequencer.note_cc_values = {}
                            
                            # このノート用のキーを生成
                            note_key = f"{row}_{col}"
                            
                            # 必要に応じてデータ構造を初期化
                            if note_key not in self.sequencer.note_cc_values:
                                self.sequencer.note_cc_values[note_key] = {}
                            
                            # CC値を保存
                            self.sequencer.note_cc_values[note_key][cc] = value
                            print(f"ノートCC値を設定: トラック{row+1} ステップ{col+1} {cc}={value}")
                    
                    elif update_type == 'sequence_row':
                        row = update.get('row')
                        states = update.get('states')
                        if row is not None and states is not None:
                            for col, state in enumerate(states):
                                self.sequencer.sequence[int(row)][col] = state
                                if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][col]:
                                    button = self.sequencer.step_buttons[int(row)][col]
                                    button_color = self.sequencer.active_color if state else self.sequencer.inactive_color
                                    button.config(bg=button_color)
                    
                    elif update_type == 'note_row':
                        row = update.get('row')
                        notes = update.get('notes')
                        if row is not None and notes is not None:
                            for col, note in enumerate(notes):
                                self.sequencer.note_values[int(row)][col] = note
                                if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][col]:
                                    self.sequencer.update_button_text(int(row), col, self.sequencer.step_buttons[int(row)][col])
                                    if hasattr(self.sequencer, 'note_labels') and self.sequencer.note_labels[int(row)][col]:
                                        note_name = self.sequencer.get_note_name(int(note))
                                        self.sequencer.note_labels[int(row)][col].config(text=note_name)
                    
                    elif update_type == 'sequence_all':
                        states = update.get('states')
                        if states is not None:
                            for row, row_states in enumerate(states):
                                for col, state in enumerate(row_states):
                                    self.sequencer.sequence[row][col] = state
                                    if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[row][col]:
                                        button = self.sequencer.step_buttons[row][col]
                                        button_color = self.sequencer.active_color if state else self.sequencer.inactive_color
                                        button.config(bg=button_color)
                    
                    elif update_type == 'note_all':
                        notes = update.get('notes')
                        if notes is not None:
                            for row, row_notes in enumerate(notes):
                                for col, note in enumerate(row_notes):
                                    self.sequencer.note_values[row][col] = note
                                    if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[row][col]:
                                        self.sequencer.update_button_text(row, col, self.sequencer.step_buttons[row][col])
                                        if hasattr(self.sequencer, 'note_labels') and self.sequencer.note_labels[row][col]:
                                            note_name = self.sequencer.get_note_name(int(note))
                                            self.sequencer.note_labels[row][col].config(text=note_name)
                
                # バッチ更新後に状態を送信
                await self.send_state()
            
            elif command == 'toggle_play':
                def toggle_play():
                    self.sequencer.toggle_play()
                    if hasattr(self.sequencer, 'play_button'):
                        button_text = '停止' if self.sequencer.is_playing else '再生'
                        self.sequencer.play_button.config(text=button_text)
                self.sequencer.root.after(0, toggle_play)
                await self.send_state()
            
            elif command == 'set_bpm':
                bpm = data.get('bpm')
                if bpm and 20 <= int(bpm) <= 300:
                    def update_bpm():
                        self.sequencer.bpm = int(bpm)
                        self.sequencer.bpm_var.set(str(bpm))
                        if hasattr(self.sequencer, 'bpm_entry'):
                            self.sequencer.bpm_entry.delete(0, tk.END)
                            self.sequencer.bpm_entry.insert(0, str(bpm))
                    self.sequencer.root.after(0, update_bpm)
                    await self.send_state()
            
            elif command == 'set_clock_divide':
                divide = data.get('divide')
                if divide is not None and divide in ['1', '2', '3', 1, 2, 3]:
                    divide = int(divide) if isinstance(divide, str) else divide
                    def update_clock_divide():
                        self.sequencer.clock_divide = divide
                        self.sequencer.clock_divide_var.set(str(divide))
                        print(f"クロックディバイドを {divide} に設定しました")
                    self.sequencer.root.after(0, update_clock_divide)
                    await self.send_state()
            
            elif command == 'toggle_step':
                row = data.get('row')
                col = data.get('col')
                state = data.get('state')  # 明示的に状態を受け取る
                if row is not None and col is not None:
                    def toggle():
                        # 明示的に状態が指定されている場合はその値を使用、そうでなければトグル
                        if state is not None:
                            self.sequencer.sequence[int(row)][int(col)] = state
                        else:
                            self.sequencer.toggle_step(int(row), int(col))
                            
                        if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][int(col)]:
                            button = self.sequencer.step_buttons[int(row)][int(col)]
                            is_active = self.sequencer.sequence[int(row)][int(col)]
                            button_color = "#5a9" if is_active else "#444"
                            button.config(bg=button_color)
                    self.sequencer.root.after(0, toggle)
                    
                    # 他のクライアントに直接通知（送信元クライアントを除く）
                    if websocket in self.clients:
                        other_clients = self.clients - {websocket}
                        if other_clients:
                            # ステップの現在の状態を取得
                            current_state = self.sequencer.sequence[int(row)][int(col)]
                            notify_message = {
                                'type': 'step_update',
                                'row': int(row),
                                'col': int(col),
                                'state': current_state
                            }
                            notify_json = json.dumps(notify_message)
                            asyncio.create_task(asyncio.gather(
                                *[client.send(notify_json) for client in other_clients]
                            ))
            
            elif command == 'set_note':
                row = data.get('row')
                col = data.get('col')
                note = data.get('note')
                divide = data.get('divide')  # 分割設定を取得
                
                if row is not None and col is not None and note is not None:
                    def update_note():
                        self.sequencer.note_values[int(row)][int(col)] = int(note)
                        
                        # 分割設定も一緒に更新
                        if divide is not None:
                            self.sequencer.note_divides[int(row)][int(col)] = int(divide)
                        
                        if hasattr(self.sequencer, 'step_buttons') and self.sequencer.step_buttons[int(row)][int(col)]:
                            self.sequencer.update_button_text(int(row), int(col), self.sequencer.step_buttons[int(row)][int(col)])
                            if hasattr(self.sequencer, 'note_labels') and self.sequencer.note_labels[int(row)][int(col)]:
                                note_name = self.sequencer.get_note_name(int(note))
                                self.sequencer.note_labels[int(row)][int(col)].config(text=note_name)
                    self.sequencer.root.after(0, update_note)
                    
                    # 他のクライアントに直接通知（送信元クライアントを除く）
                    if websocket in self.clients:
                        other_clients = self.clients - {websocket}
                        if other_clients:
                            # ノート値の更新通知
                            note_message = {
                                'type': 'note_update',
                                'row': int(row),
                                'col': int(col),
                                'note': int(note)
                            }
                            note_json = json.dumps(note_message)
                            
                            # 分割設定の更新通知（設定されている場合）
                            if divide is not None:
                                divide_message = {
                                    'type': 'divide_update',
                                    'row': int(row),
                                    'col': int(col),
                                    'divide': int(divide)
                                }
                                divide_json = json.dumps(divide_message)
                                
                                # 両方のメッセージを送信
                                asyncio.create_task(asyncio.gather(
                                    *[client.send(note_json) for client in other_clients],
                                    *[client.send(divide_json) for client in other_clients]
                                ))
                            else:
                                # ノート値のみ送信
                                asyncio.create_task(asyncio.gather(
                                    *[client.send(note_json) for client in other_clients]
                                ))
                                
            elif command == 'set_divide':
                # 分割設定のみを更新するコマンド
                row = data.get('row')
                col = data.get('col')
                divide = data.get('divide')
                
                if row is not None and col is not None and divide is not None:
                    def update_divide():
                        self.sequencer.note_divides[int(row)][int(col)] = int(divide)
                        
                        # UIを更新（もし実装されていれば）
                        if hasattr(self.sequencer, 'update_divide_ui'):
                            self.sequencer.update_divide_ui(int(row), int(col), int(divide))
                    
                    self.sequencer.root.after(0, update_divide)
                    
                    # 他のクライアントに直接通知（送信元クライアントを除く）
                    if websocket in self.clients:
                        other_clients = self.clients - {websocket}
                        if other_clients:
                            divide_message = {
                                'type': 'divide_update',
                                'row': int(row),
                                'col': int(col),
                                'divide': int(divide)
                            }
                            divide_json = json.dumps(divide_message)
                            asyncio.create_task(asyncio.gather(
                                *[client.send(divide_json) for client in other_clients]
                            ))
            
            elif command == 'update_cc':
                track = data.get('track')
                cc = data.get('cc')
                value = data.get('value')
                if track and cc and value is not None:
                    print(f"CC更新リクエスト: {track}/{cc}={value}")
                    
                    # 前回と同じ値の場合は処理をスキップ
                    cc_key = f"cc{int(cc.replace('cc', ''))}" if cc.startswith('cc') else f"cc{int(cc)}"
                    current_value = self.sequencer.cc_values.get(track, {}).get(cc_key, None)
                    if current_value == int(value):
                        print(f"値が変わっていないためスキップ: {track}/{cc_key}={value}")
                        return
                    
                    def update_cc():
                        try:
                            # 正規化されたCC番号を取得
                            cc_num = int(cc.replace('cc', '')) if cc.startswith('cc') else int(cc)
                            cc_key = f"cc{cc_num}"
                            
                            # CCの値を更新
                            self.sequencer.update_cc(track, cc_key, int(value))
                            print(f"CC値を更新しました: {track}/{cc_key}={value}")
                            
                            # UIスライダーがあれば更新
                            if hasattr(self.sequencer, 'cc_sliders') and track in self.sequencer.cc_sliders:
                                cc_sliders_entry = self.sequencer.cc_sliders[track]
                                if isinstance(cc_sliders_entry, dict) and cc_key in cc_sliders_entry:
                                    slider = cc_sliders_entry[cc_key]
                                    if hasattr(slider, 'set'):
                                        slider.set(int(value))
                                        print(f"スライダーUI更新: {track}/{cc_key}={value}")
                                    elif isinstance(slider, tk.IntVar):
                                        slider.set(int(value))
                                        print(f"IntVar更新: {track}/{cc_key}={value}")
                        except Exception as e:
                            print(f"CC更新エラー ({track}/{cc}/{value}): {e}")
                    
                    # tkinterスレッドで実行
                    self.sequencer.root.after(0, update_cc)
                    
                    # CC更新通知は他のクライアントにのみ送信（送信元は既に更新済み）
                    if websocket in self.clients:
                        other_clients = self.clients - {websocket}
                        # 他のクライアントがある場合だけ送信
                        if other_clients:
                            notify_message = {
                                'type': 'cc_update', 
                                'track': track, 
                                'cc': cc, 
                                'value': int(value)
                            }
                            await asyncio.gather(
                                *[client.send(json.dumps(notify_message)) for client in other_clients]
                            )
            
            elif command == 'send_preset':
                preset = data.get('preset')
                if preset:
                    def send_preset():
                        self.sequencer.send_preset(int(preset))
                        if hasattr(self.sequencer, 'preset_var'):
                            self.sequencer.preset_var.set(str(preset))
                    self.sequencer.root.after(0, send_preset)
                    await self.send_state()
            
            elif command == 'change_midi_output':
                port = data.get('port')
                if port:
                    def change_port():
                        self.sequencer.change_midi_port(port)
                        if hasattr(self.sequencer, 'port_var') and port in self.sequencer.available_ports:
                            self.sequencer.port_var.set(port)
                    self.sequencer.root.after(0, change_port)
                    await self.send_state()
            
            elif command == 'change_midi_input':
                port = data.get('port')
                if port:
                    def change_input():
                        self.sequencer.change_midi_input_port(port)
                        if hasattr(self.sequencer, 'input_port_var') and (port == 'なし' or port in self.sequencer.available_input_ports):
                            self.sequencer.input_port_var.set(port)
                    self.sequencer.root.after(0, change_input)
                    await self.send_state()
            
            elif command == 'toggle_midi_clock':
                enabled = data.get('enabled')
                if enabled is not None:
                    def toggle_clock():
                        self.sequencer.clock_var.set(enabled)
                        self.sequencer.toggle_midi_clock()
                        if hasattr(self.sequencer, 'clock_check'):
                            state = tk.ACTIVE if enabled else tk.NORMAL
                            self.sequencer.clock_check.config(state=state)
                    self.sequencer.root.after(0, toggle_clock)
                    await self.send_state()
            
            elif command == 'get_available_ports':
                ports = {
                    'type': 'ports',
                    'output': self.sequencer.available_ports,
                    'input': ['なし'] + self.sequencer.available_input_ports
                }
                await websocket.send(json.dumps(ports))
            
            elif command == 'apply_note_cc':
                row = data.get('row')
                col = data.get('col')
                if row is not None and col is not None:
                    note_key = f"{row}_{col}"
                    if hasattr(self.sequencer, 'note_cc_values') and note_key in self.sequencer.note_cc_values:
                        cc_values = self.sequencer.note_cc_values[note_key]
                        
                        # トラック名を取得
                        track_idx = int(row)
                        if 0 <= track_idx < len(self.sequencer.track_names):
                            track_name = self.sequencer.track_names[track_idx]
                            
                            # すべてのCC値を適用
                            for cc, value in cc_values.items():
                                def apply_cc():
                                    try:
                                        self.sequencer.update_cc(track_name, cc, int(value))
                                        print(f"ノートCC適用: {track_name} {cc}={value}")
                                    except Exception as e:
                                        print(f"ノートCC適用エラー: {e}")
                                
                                self.sequencer.root.after(0, apply_cc)
                            
                            await websocket.send(json.dumps({
                                'type': 'note_cc_applied',
                                'row': row,
                                'col': col,
                                'cc_count': len(cc_values)
                            }))
                    else:
                        await websocket.send(json.dumps({
                            'type': 'error',
                            'message': f'No CC values found for note at row {row}, col {col}'
                        }))
            
            else:
                await websocket.send(json.dumps({'type': 'error', 'message': f'Unknown command: {command}'}))
        
        except json.JSONDecodeError:
            await websocket.send(json.dumps({'type': 'error', 'message': 'Invalid JSON'}))
        except Exception as e:
            await websocket.send(json.dumps({'type': 'error', 'message': str(e)}))
    
    async def ws_handler(self, websocket, path):
        """WebSocket接続ハンドラ"""
        try:
            # クライアント登録（この中でバリデーションが行われる）
            await self.register(websocket)
            
            # 非アクティブなクライアントを処理するタイマー
            last_activity = time.time()
            last_ping = time.time()
            ping_interval = 10  # 10秒ごとにpingを送信
            
            try:
                async for message in websocket:
                    # メッセージを受信したため、アクティビティタイムスタンプを更新
                    last_activity = time.time()
                    
                    # 現在時刻を取得
                    current_time = time.time()
                    
                    # 定期的にpingを送信して接続状態を確認
                    if current_time - last_ping >= ping_interval:
                        try:
                            await websocket.ping()
                            last_ping = current_time
                            print(f"Pingを送信: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                        except websockets.exceptions.ConnectionClosed:
                            print(f"Ping中に接続が閉じられました: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                            break
                    
                    # 長時間アクティビティがない場合
                    if current_time - last_activity > 30:
                        print(f"長時間アクティビティなし: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                        # 接続の状態をチェック
                        try:
                            pong_waiter = await websocket.ping()
                            await asyncio.wait_for(pong_waiter, timeout=1.0)
                            # Pongを受信した場合、アクティビティタイマーをリセット
                            last_activity = current_time
                            print(f"Pong受信 - 接続アクティブ: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                            # Ping失敗 - 接続が切れている
                            print(f"非アクティブなクライアント接続を切断します: {self.client_info.get(websocket, {}).get('id', 'unknown')}")
                            break
                    
                    # メッセージ処理
                    await self.handle_message(websocket, message)
                    
            except websockets.exceptions.ConnectionClosed as e:
                # 通常の切断処理
                client_info = self.client_info.get(websocket, {})
                client_id = client_info.get('id', 'unknown')
                print(f"クライアント接続が閉じられました: {client_id} (コード: {e.code}, 理由: {e.reason})")
            except Exception as e:
                # その他の例外処理
                print(f"WebSocketハンドラーでエラーが発生しました: {e}")
                import traceback
                traceback.print_exc()
        
        finally:
            # クライアントの登録解除
            await self.unregister(websocket)
    
    def start(self):
        """WebSocketサーバーを開始する"""
        try:
            # 非同期ループを取得または作成
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # サーバー起動関数を定義
            async def start_server():
                # WebSocketサーバーを起動
                print(f"WebSocketサーバーを起動中: {self.host}:{self.port}")
                self.server = await websockets.serve(
                    self.handler, self.host, self.port
                )
                self.is_running = True
                print(f"WebSocketサーバーが起動しました: {self.host}:{self.port}")
                
                # 無限ループでサーバーを実行
                await asyncio.Future()  # これは決して完了しない
            
            # 新しいスレッドでイベントループを実行
            def run_event_loop():
                try:
                    loop.run_until_complete(start_server())
                except Exception as e:
                    print(f"WebSocketサーバー起動エラー: {e}")
                    import traceback
                    traceback.print_exc()
                    self.is_running = False
            
            # 別スレッドで実行
            threading.Thread(target=run_event_loop, daemon=True).start()
            print(f"WebSocketサーバースレッドを開始しました: {self.host}:{self.port}")
            
        except Exception as e:
            print(f"WebSocketサーバー起動中にエラーが発生: {e}")
            import traceback
            traceback.print_exc()
            self.is_running = False
    
    def stop(self):
        """WebSocketサーバーを停止する"""
        try:
            if self.server:
                print("WebSocketサーバーを停止中...")
                # 非同期的にサーバーを停止
                async def close_server():
                    self.server.close()
                    await self.server.wait_closed()
                
                # イベントループを取得
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # ループが実行中の場合、別のループで停止タスクを実行
                        asyncio.run_coroutine_threadsafe(close_server(), loop)
                    else:
                        # ループが実行中でない場合、単純に実行
                        loop.run_until_complete(close_server())
                except Exception as e:
                    print(f"サーバー停止中にイベントループエラー: {e}")
                    # バックアップとして新しいループを作成
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(close_server())
                    loop.close()
            
            # 停止完了
            self.server = None
            self.is_running = False
            print("WebSocketサーバーを停止しました")
        except Exception as e:
            print(f"WebSocketサーバー停止中にエラー: {e}")
            import traceback
            traceback.print_exc()
            self.is_running = False
    
    async def periodic_state_update(self):
        """定期的に状態を更新する"""
        try:
            last_step = -1  # 前回のステップ
            last_playing_state = None  # 前回の再生状態
            update_counter = 0  # 更新カウンター（デバッグ用）
            last_full_update = 0
            
            while True:
                # 状態更新間隔だけ待機
                await asyncio.sleep(self.state_update_interval)
                
                # クライアントがなければ何もしない
                if not self.clients:
                    continue
                
                # 現在時刻を取得
                current_time = time.time()
                current_step = self.sequencer.current_step
                is_playing = self.sequencer.is_playing
                
                # ステップが変化したとき、または再生状態が変化したときのみ更新
                step_changed = current_step != last_step
                playing_changed = is_playing != last_playing_state
                
                # 1秒ごとに強制的に完全更新（ハートビート）
                force_full_update = (current_time - last_full_update) >= 1.0
                
                # 0.2秒ごとに軽量更新
                force_light_update = (current_time - self.last_state_update) >= 0.2
                
                if step_changed or playing_changed or force_light_update or force_full_update:
                    update_counter += 1
                    
                    if force_full_update:
                        # 完全な状態を送信
                        await self.send_state()
                        last_full_update = current_time
                        print(f"完全な状態更新を送信 #{update_counter}")
                    else:
                        # 軽量更新メッセージを作成（必要最小限の情報）
                        light_update = {
                            'type': 'state_update',
                            'current_step': current_step,
                            'is_playing': is_playing,
                            'bpm': self.sequencer.bpm,
                            'update_id': update_counter
                        }
                        
                        try:
                            # 軽量状態を送信
                            state_json = json.dumps(light_update)
                            for client in self.clients:
                                try:
                                    await client.send(state_json)
                                except Exception as e:
                                    print(f"クライアントへの軽量状態送信中にエラーが発生: {e}")
                            
                            # デバッグ情報を制限（あまりに頻繁な更新はログを埋め尽くす）
                            if step_changed or playing_changed or (update_counter % 10 == 0):
                                update_reason = "軽量更新"
                                if step_changed:
                                    update_reason = "ステップ変更"
                                elif playing_changed:
                                    update_reason = "再生状態変更"
                                    
                                print(f"軽量状態更新送信 #{update_counter}: {update_reason}, ステップ={current_step}, 再生={is_playing}")
                            
                        except Exception as e:
                            print(f"軽量状態更新の送信中にエラー: {e}")
                    
                    # 前回の値を更新
                    last_step = current_step
                    last_playing_state = is_playing
                    self.last_state_update = current_time
                    
        except asyncio.CancelledError:
            print("状態更新タスクがキャンセルされました")
        except Exception as e:
            print(f"状態更新中にエラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
            
            # エラーが発生した場合はタスクを再作成
            self.state_update_task = None
            # 一定時間後に再度タスクを開始
            await asyncio.sleep(1.0)
            if self.clients:
                print("状態更新タスクを再開します")
                self.state_update_task = asyncio.create_task(self.periodic_state_update())

    async def get_state(self):
        """現在のシーケンサーの状態を取得する"""
        sequence_data = []
        note_values = []
        note_divides = []  # 分割設定を追加
        
        # シーケンス (ステップのオン/オフ状態)
        for row in self.sequencer.sequence:
            sequence_data.append(row)
            
        # ノート値
        for row in self.sequencer.note_values:
            note_values.append(row)
        
        # 分割設定
        for row in self.sequencer.note_divides:
            note_divides.append(row)
            
        # 利用可能なMIDIポート
        available_midi_outputs = []
        available_midi_inputs = []
        
        try:
            available_midi_outputs = mido.get_output_names()
            available_midi_inputs = mido.get_input_names()
        except Exception as e:
            print(f"MIDIポート一覧取得エラー: {e}")
        
        # CC値の取得
        cc_values = {}
        for track_name in self.sequencer.track_names:
            cc_values[track_name] = self.sequencer.cc_values.get(track_name, {})
            
        return {
            'type': 'state',
            'sequence': sequence_data,
            'note_values': note_values,
            'note_divides': note_divides,  # 分割設定を追加
            'cc_values': cc_values,
            'current_step': self.sequencer.current_step,
            'is_playing': self.sequencer.is_playing,
            'bpm': self.sequencer.bpm,
            'clock_divide': self.sequencer.clock_divide,
            'available_midi_outputs': available_midi_outputs,
            'available_midi_inputs': available_midi_inputs,
            'midi_output': self.sequencer.port_name,
            'midi_input': self.sequencer.input_port_name,
            'midi_clock_enabled': self.sequencer.midi_clock_enabled
        }

    async def send_to_all(self, message):
        """すべてのクライアントにメッセージを送信する"""
        if not self.clients:
            return

        try:
            # 辞書型の場合はJSONに変換
            if isinstance(message, dict):
                message_json = json.dumps(message)
            else:
                message_json = message
                
            for client in self.clients:
                try:
                    await client.send(message_json)
                except Exception as e:
                    print(f"クライアントへのメッセージ送信中にエラー: {e}")
                    # 接続が切れている場合はクライアントを削除
                    try:
                        await self.unregister(client)
                    except:
                        pass
        except Exception as e:
            print(f"全クライアントへのメッセージ送信中にエラー: {e}")
            
    async def handler(self, websocket, path=None):
        """WebSocketクライアント接続を処理する"""
        print(f"新しいクライアント接続: {websocket.remote_address}")
        
        # クライアントを登録
        await self.register(websocket)
        
        try:
            # クライアントからのメッセージをリスニング
            async for message in websocket:
                try:
                    await self.handle_message(websocket, message)
                except json.JSONDecodeError:
                    print(f"無効なJSONメッセージを受信: {message}")
                    # JSONエラーを通知
                    error_message = {
                        'type': 'error',
                        'message': '無効なJSONメッセージを受信しました'
                    }
                    await websocket.send(json.dumps(error_message))
                except Exception as e:
                    print(f"メッセージ処理エラー: {e}")
                    import traceback
                    traceback.print_exc()
                    # エラーを通知
                    error_message = {
                        'type': 'error',
                        'message': f'サーバーエラー: {str(e)}'
                    }
                    await websocket.send(json.dumps(error_message))
        except websockets.exceptions.ConnectionClosed as e:
            print(f"接続が閉じられました: {e.code} {e.reason}")
        except Exception as e:
            print(f"WebSocket通信エラー: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # クライアントを登録解除
            await self.unregister(websocket)

if __name__ == "__main__":
    # HTMLクライアントを生成
    generate_html_client()
    
    # IPアドレスを取得
    local_ip = get_local_ip()
    
    # 簡易HTTPサーバーを起動
    http_port = 8000
    http_handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("0.0.0.0", http_port), http_handler)
    
    # HTTPサーバーを別スレッドで起動
    http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    http_thread.start()
    print(f"HTTPサーバーを開始しました: http://{local_ip}:{http_port}")
    print(f"ローカルアクセス: http://localhost:{http_port}")
    
    # ブラウザでHTMLクライアントを開く
    webbrowser.open(f"http://localhost:{http_port}/midi_sequencer_client.html")
    
    # tkinterウィンドウを作成
    root = tk.Tk()
    sequencer = MidiSequencer(root)
    
    # WebSocketサーバーを作成
    server = WebSocketServer(sequencer, host='0.0.0.0', port=8765)
    print(f"WebSocketサーバーを開始しました: ws://{local_ip}:8765")
    
    # シーケンサーにWebSocketサーバーへの参照を設定
    sequencer.websocket_server = server
    
    # サーバーを別スレッドで開始
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()
    
    # アプリケーション終了時の処理
    def on_closing():
        if sequencer.is_playing:
            sequencer.toggle_play()  # 再生を停止
        if sequencer.input_port:
            sequencer.input_port.close()  # 入力ポートを閉じる
        server.stop()  # WebSocketサーバーを停止
        httpd.shutdown()  # HTTPサーバーを停止
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # tkinterメインループを開始
    root.mainloop() 