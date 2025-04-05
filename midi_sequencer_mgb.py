import tkinter as tk
import mido
import threading
import time
import asyncio
from tkinter import simpledialog, messagebox

# WebSocketサーバー関連の追加（レガシーコード - 現在は不使用）
"""
import asyncio
import websockets
import json
import threading
import os
import sys
# 現在のディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# WebSocketサーバーモジュールをインポート
try:
    import websocket_server
except ImportError:
    print("websocket_server.pyが見つかりません。WebSocket APIは無効になります。")
    websocket_server = None
"""
# レガシーコードを無効化
websocket_server = None

class MidiSequencer:
    def __init__(self, root):
        self.root = root
        self.root.title("mGB MIDI シーケンサー")
        self.root.geometry("900x600")
        
        # WebSocketサーバーへの参照
        self.websocket_server = None
        
        # MIDIデバイスの設定
        self.setup_midi()
        
        # シーケンサーの状態
        self.is_playing = False
        self.current_step = 0
        self.bpm = 120
        self.steps = 16
        
        # クロックディバイド設定（1=通常、2=2連符、3=3連符）
        self.clock_divide = 1
        
        # mGBの5つのチャンネルに対応
        self.tracks = 5
        self.track_names = ["PU1", "PU2", "WAV", "NOISE", "POLY"]
        self.midi_channels = [0, 1, 2, 3, 4]  # MIDIチャンネル1-5 (0-4で表現)
        
        # 各トラックのノート設定
        self.sequence = [[False for _ in range(self.steps)] for _ in range(self.tracks)]
        
        # デフォルトノート値 (C, E, G, C, E) をデフォルト値として使用
        self.default_notes = [60, 64, 67, 72, 76]
        
        # 各ステップごとのノート設定を保存する2次元配列
        # [トラック][ステップ] -> ノート番号
        self.note_values = [[self.default_notes[track] for _ in range(self.steps)] for track in range(self.tracks)]
        
        # 各ステップごとの分割設定（1=通常、2=2連符、3=3連符）
        self.note_divides = [[1 for _ in range(self.steps)] for track in range(self.tracks)]
        
        # ボタンの色設定
        self.active_color = "#5a9"  # アクティブなステップの色
        self.inactive_color = "#444"  # 非アクティブなステップの色
        
        # コントロールチェンジ値
        self.cc_values = {
            "PU1": {"cc1": 64, "cc2": 64, "cc3": 0, "cc4": 2, "cc10": 64, "cc64": 0},
            "PU2": {"cc1": 64, "cc2": 64, "cc4": 2, "cc10": 64, "cc64": 0},
            "WAV": {"cc1": 0, "cc2": 0, "cc3": 0, "cc4": 2, "cc10": 64, "cc64": 0},
            "NOISE": {"cc2": 64, "cc10": 64, "cc64": 0},
            "POLY": {"cc1": 64, "cc10": 64, "cc64": 0}
        }
        
        # ピッチベンド値（-8192〜8191）
        self.pitch_bend_values = {
            "PU1": 0,
            "PU2": 0,
            "WAV": 0,
            "NOISE": 0,
            "POLY": 0
        }
        
        # サステイン状態を追跡
        self.sustain_active = {track: False for track in self.track_names}
        
        # アクティブノート（サステイン中のノートを追跡）
        self.active_notes = {track: set() for track in self.track_names}
        
        # UIの作成
        self.create_ui()
        
        # WebSocketサーバーの起動は新しいアーキテクチャに移行済み
        # self.start_websocket_server()
        
    def setup_midi(self):
        """MIDIデバイスのセットアップ"""
        # 利用可能なMIDI出力デバイスを取得
        self.available_ports = mido.get_output_names()
        print("利用可能なMIDI出力ポート:", self.available_ports)
        
        # 利用可能なMIDI入力デバイスを取得
        self.available_input_ports = mido.get_input_names()
        print("利用可能なMIDI入力ポート:", self.available_input_ports)
        
        # MIDI出力ポート
        self.port_name = None
        self.output_port = None  # ポートオブジェクトを保持
        
        # mGBポートを探す（"Arduinoboy"などを含むポート名を優先）
        mgb_port = None
        for port in self.available_ports:
            if "arduinoboy" in port.lower() or "mgb" in port.lower():
                mgb_port = port
                break
        
        # mGBポートを見つけたか、それ以外のポートを使用
        if mgb_port:
            try:
                self.port_name = mgb_port
                print(f"mGB用ポート '{self.port_name}' を検出しました")
                # 一度オープンしてテスト
                self.output_port = mido.open_output(self.port_name)
                print(f"MIDI出力ポート '{self.port_name}' に接続しました")
            except Exception as e:
                print(f"mGB用ポートに接続できません: {e}")
                self.port_name = None
                self.output_port = None
        elif self.available_ports:
            try:
                self.port_name = self.available_ports[0]
                print(f"デフォルトポート '{self.port_name}' を使用します")
                # 一度オープンしてテスト
                self.output_port = mido.open_output(self.port_name)
                print(f"MIDI出力ポート '{self.port_name}' に接続しました")
            except Exception as e:
                print(f"デフォルトMIDI出力ポートに接続できません: {e}")
                self.port_name = None
                self.output_port = None
        else:
            # 利用可能なポートがない場合
            print("利用可能なMIDI出力ポートがありません")
            self.port_name = None
        
        # 初期接続が成功したらポートを閉じる
        if self.output_port:
            self.output_port.close()
            self.output_port = None
            
        # MIDI入力ポート
        self.input_port_name = None
        self.input_port = None
        
        # MIDI Clock用の変数
        self.last_clock_time = None
        self.clock_count = 0
        self.midi_clock_enabled = False
    
    def create_ui(self):
        """UIコンポーネントの作成"""
        # コントロールフレーム
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        # 再生/停止ボタン
        self.play_button = tk.Button(control_frame, text="再生", command=self.toggle_play)
        self.play_button.grid(row=0, column=0, padx=5)
        
        # BPM設定
        tk.Label(control_frame, text="BPM:").grid(row=0, column=1, padx=5)
        self.bpm_var = tk.StringVar(value=str(self.bpm))
        bpm_entry = tk.Entry(control_frame, textvariable=self.bpm_var, width=5)
        bpm_entry.grid(row=0, column=2, padx=5)
        bpm_entry.bind("<Return>", self.update_bpm)
        
        # クロックディバイド設定
        tk.Label(control_frame, text="分割:").grid(row=0, column=3, padx=5)
        self.clock_divide_var = tk.StringVar(value="1")
        clock_divide_menu = tk.OptionMenu(control_frame, self.clock_divide_var, "1", "2", "3", command=self.update_clock_divide)
        clock_divide_menu.grid(row=0, column=4, padx=5)
        
        # MIDIデバイス選択
        tk.Label(control_frame, text="MIDI出力:").grid(row=0, column=5, padx=5)
        self.port_var = tk.StringVar()
        if self.available_ports:
            self.port_var.set(self.port_name or self.available_ports[0])
        port_menu = tk.OptionMenu(control_frame, self.port_var, *self.available_ports, command=self.change_midi_port)
        port_menu.grid(row=0, column=6, padx=5)
        
        # MIDI入力デバイス選択
        tk.Label(control_frame, text="MIDI入力:").grid(row=0, column=7, padx=5)
        self.input_port_var = tk.StringVar(value="なし")
        input_ports = ["なし"] + self.available_input_ports
        input_port_menu = tk.OptionMenu(control_frame, self.input_port_var, *input_ports, command=self.change_midi_input_port)
        input_port_menu.grid(row=0, column=8, padx=5)
        
        # MIDI Clock有効/無効切り替え
        self.clock_var = tk.BooleanVar(value=False)
        clock_check = tk.Checkbutton(control_frame, text="MIDI Clock同期", variable=self.clock_var, command=self.toggle_midi_clock)
        clock_check.grid(row=0, column=9, padx=5)
        
        # mGB情報表示ボタン
        info_button = tk.Button(control_frame, text="mGB情報", command=self.show_mgb_info)
        info_button.grid(row=0, column=10, padx=5)
        
        # プリセット選択ボタン
        tk.Label(control_frame, text="プリセット:").grid(row=1, column=0, padx=5, pady=5)
        preset_frame = tk.Frame(control_frame)
        preset_frame.grid(row=1, column=1, columnspan=3, padx=5)
        
        for i in range(1, 16):  # mGBは1-15のプリセットをサポート
            btn = tk.Button(preset_frame, text=str(i), width=2, 
                           command=lambda preset=i: self.send_preset(preset))
            btn.pack(side=tk.LEFT, padx=2)
        
        # CCフレームをグリッドに配置
        cc_frame = tk.Frame(self.root)
        cc_frame.pack(pady=10)
        
        # 各トラックのCCコントロール
        self.cc_sliders = {}
        
        for i, track in enumerate(self.track_names):
            track_frame = tk.LabelFrame(cc_frame, text=track)
            track_frame.grid(row=0, column=i, padx=10, pady=5)
            
            # 各トラックに対応するCCスライダーを作成
            sliders = {}
            row = 0
            
            # READMEに基づいて、各トラックで利用可能なCCを設定
            if track == "PU1":
                ccs = {
                    "cc1": "Pulse Width (0,32,64,127)",
                    "cc2": "Envelope (0-127)",
                    "cc3": "Pitch Sweep (0-127)",
                    "cc4": "PB Range (0-48)",
                    "cc10": "Pan (0-127)",
                    "cc64": "Sustain (0/127)"  # READMEによるとON/OFF
                }
            elif track == "PU2":
                ccs = {
                    "cc1": "Pulse Width (0,32,64,127)",
                    "cc2": "Envelope (0-127)",
                    "cc4": "PB Range (0-48)",
                    "cc10": "Pan (0-127)",
                    "cc64": "Sustain (0/127)"
                }
            elif track == "WAV":
                ccs = {
                    "cc1": "Shape (0-127)",
                    "cc2": "Offset (0-127)",
                    "cc3": "Pitch Sweep (0-127)",
                    "cc4": "PB Range (0-48)",
                    "cc10": "Pan (0-127)",
                    "cc64": "Sustain (0/127)"
                }
            elif track == "NOISE":
                ccs = {
                    "cc2": "Envelope (0-127)",
                    "cc10": "Pan (0-127)",
                    "cc64": "Sustain (0/127)"
                }
            else:  # POLY
                ccs = {
                    "cc1": "Pulse Width (0-127)",
                    "cc10": "Pan (0-127)",
                    "cc64": "Sustain (0/127)"
                }
            
            for cc, label in ccs.items():
                # CC64（サステイン）は特別扱い - トグルボタンにする
                if cc == "cc64":
                    cc_var = tk.IntVar(value=self.cc_values[track].get(cc, 0))
                    
                    # サステインON/OFFを切り替えるボタン
                    sustain_frame = tk.Frame(track_frame)
                    sustain_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
                    
                    tk.Label(sustain_frame, text=label).pack(side=tk.LEFT)
                    
                    # ONボタン
                    on_btn = tk.Button(sustain_frame, text="ON", width=3,
                                     command=lambda t=track, c=cc: self.set_sustain(t, c, 127))
                    on_btn.pack(side=tk.LEFT, padx=2)
                    
                    # OFFボタン
                    off_btn = tk.Button(sustain_frame, text="OFF", width=3,
                                      command=lambda t=track, c=cc: self.set_sustain(t, c, 0))
                    off_btn.pack(side=tk.LEFT, padx=2)
                    
                    sliders[cc] = cc_var
                # CC1 (Pulse Width)は特別値のみ許可
                elif cc == "cc1" and (track == "PU1" or track == "PU2"):
                    cc_var = tk.IntVar(value=self.cc_values[track].get(cc, 64))
                    
                    # パルス幅用のコンポジットコントロール
                    pw_frame = tk.Frame(track_frame)
                    pw_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
                    
                    tk.Label(pw_frame, text=label).pack(side=tk.LEFT)
                    
                    # スライダーを追加
                    slider = tk.Scale(pw_frame, from_=0, to=127, orient=tk.HORIZONTAL, 
                                     variable=cc_var, length=100,
                                     command=lambda v, t=track, c=cc: self.update_cc(t, c, v))
                    slider.pack(side=tk.LEFT, padx=5, pady=2)
                    
                    sliders[cc] = slider
                else:
                    # 通常のスライダー
                    tk.Label(track_frame, text=label).grid(row=row, column=0, sticky="w")
                    
                    # スライダーの初期値設定
                    cc_var = tk.IntVar(value=self.cc_values[track].get(cc, 64))
                    
                    # PB Range (cc4)の場合は最大値を48に制限（README.mdより）
                    max_val = 48 if cc == "cc4" else 127
                    
                    slider = tk.Scale(track_frame, from_=0, to=max_val, orient=tk.HORIZONTAL, 
                                     variable=cc_var, command=lambda v, t=track, c=cc: self.update_cc(t, c, v))
                    slider.grid(row=row, column=1, padx=5, pady=2)
                    sliders[cc] = slider
                
                row += 1
            
            self.cc_sliders[track] = sliders
        
        # シーケンサーグリッド
        self.grid_frame = tk.Frame(self.root)
        self.grid_frame.pack(pady=20)
        
        # トラックラベル
        for i in range(self.tracks):
            tk.Label(self.grid_frame, text=f"{self.track_names[i]} (CH{i+1})").grid(row=i, column=0, padx=5, pady=5)
        
        # ステップボタン
        self.step_buttons = []
        for i in range(self.tracks):
            row_buttons = []
            for j in range(self.steps):
                # ステップボタンにはボタンクリックとダブルクリックの両方を設定
                btn = tk.Button(self.grid_frame, width=3, height=1, bg="white",
                              command=lambda r=i, c=j: self.toggle_step(r, c))
                btn.grid(row=i, column=j+1, padx=2, pady=2)
                
                # 右クリックでノート設定ダイアログを表示
                btn.bind("<Button-3>", lambda event, r=i, c=j: self.set_note_dialog(r, c))
                
                # ボタンのテキストにノート番号を表示
                self.update_button_text(i, j, btn)
                
                row_buttons.append(btn)
            self.step_buttons.append(row_buttons)
        
        # ステップインジケーター
        self.step_indicators = []
        for j in range(self.steps):
            indicator = tk.Label(self.grid_frame, text=str(j+1), bg="lightgray")
            indicator.grid(row=self.tracks, column=j+1, padx=2, pady=2)
            self.step_indicators.append(indicator)
            
        # ノート設定の説明
        note_info = tk.Label(self.grid_frame, text="右クリック: ノート設定 | 左クリック: ステップON/OFF", fg="blue")
        note_info.grid(row=self.tracks + 1, column=0, columnspan=self.steps + 1, pady=5)
    
    def toggle_step(self, row, col):
        """ステップのオン/オフを切り替える"""
        self.sequence[row][col] = not self.sequence[row][col]
        color = self.active_color if self.sequence[row][col] else self.inactive_color
        self.step_buttons[row][col].config(bg=color)
        
        # 現在のノート値を表示するため、ボタンテキストを更新
        self.update_button_text(row, col, self.step_buttons[row][col])
        
        # WebSocketクライアントに通知
        if hasattr(self, 'websocket_server') and self.websocket_server:
            def notify_clients():
                try:
                    # ステップ更新通知
                    step_message = {
                        'type': 'step_update',
                        'row': row,
                        'col': col,
                        'state': self.sequence[row][col]
                    }
                    asyncio.run(self.websocket_server.send_to_all(step_message))
                except Exception as e:
                    print(f"WebSocketステップ更新通知エラー: {e}")
            
            # 別スレッドで非同期処理を実行
            threading.Thread(target=notify_clients, daemon=True).start()
    
    def set_note_dialog(self, row, col):
        """ノート設定ダイアログを表示する"""
        # ノート名のリスト（オクターブ2-8の範囲、C-2=0, G8=127）
        note_names = []
        for octave in range(2, 9):  # オクターブ2から8まで
            for note in ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']:
                note_idx = len(note_names)
                if note_idx <= 127:  # MIDIノート範囲内のみ
                    note_names.append(f"{note}{octave}")
        
        # 現在のノート値
        current_note = self.note_values[row][col]
        
        # 現在の分割設定
        current_divide = self.note_divides[row][col]
        
        # ノート名に変換（値が範囲内の場合）
        current_note_name = ""
        if 0 <= current_note <= 127:
            octave = (current_note // 12) - 1  # オクターブは-1から始まる
            note_idx = current_note % 12
            note_letters = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            current_note_name = f"{note_letters[note_idx]}{octave}"
        
        # 1つのダイアログでノート設定と分割設定を行う
        dialog = tk.Toplevel(self.root)
        dialog.title(f"ノート設定: {self.track_names[row]} ステップ {col+1}")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()  # モーダルダイアログにする
        
        # 結果を保存する変数
        result_note = tk.IntVar(value=current_note)
        result_divide = tk.IntVar(value=current_divide)
        
        # ノート設定フレーム
        note_frame = tk.Frame(dialog)
        note_frame.pack(pady=10, fill=tk.X, padx=20)
        
        tk.Label(note_frame, text=f"ノート番号 (0-127)").grid(row=0, column=0, sticky="w")
        note_entry = tk.Entry(note_frame, textvariable=result_note, width=5)
        note_entry.grid(row=0, column=1, padx=5)
        
        # 現在のノート名を表示
        note_name_label = tk.Label(note_frame, text=f"現在: {current_note} ({current_note_name})")
        note_name_label.grid(row=0, column=2, padx=5, sticky="w")
        
        # 分割設定フレーム
        divide_frame = tk.Frame(dialog)
        divide_frame.pack(pady=10, fill=tk.X, padx=20)
        
        tk.Label(divide_frame, text="分割設定:").grid(row=0, column=0, sticky="w")
        
        # 色の定義
        normal_color = "#f0f0f0"  # 通常の背景色
        duplet_color = "#90ee90"  # 2連符用の色（薄緑）
        triplet_color = "#add8e6"  # 3連符用の色（薄青）
        
        # 分割設定用のラジオボタン
        normal_rb = tk.Radiobutton(divide_frame, text="通常", variable=result_divide, value=1, 
                                bg=normal_color, selectcolor=normal_color, padx=10, pady=5)
        normal_rb.grid(row=0, column=1, padx=5)
        
        duplet_rb = tk.Radiobutton(divide_frame, text="2連符", variable=result_divide, value=2, 
                                bg=duplet_color, selectcolor=duplet_color, padx=10, pady=5)
        duplet_rb.grid(row=0, column=2, padx=5)
        
        triplet_rb = tk.Radiobutton(divide_frame, text="3連符", variable=result_divide, value=3, 
                                bg=triplet_color, selectcolor=triplet_color, padx=10, pady=5)
        triplet_rb.grid(row=0, column=3, padx=5)
        
        # 説明ラベル
        explanation = tk.Label(dialog, text="分割設定は各ステップの音符の長さを分割します。\n2連符、3連符の設定は、ボタンの色で表示されます。", 
                            justify=tk.LEFT, fg="gray")
        explanation.pack(pady=10, padx=20, anchor="w")
        
        # ボタンフレーム
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        
        # OKボタンとキャンセルボタン
        def on_ok():
            new_note = result_note.get()
            new_divide = result_divide.get()
            
            # 入力値のバリデーション
            if 0 <= new_note <= 127 and 1 <= new_divide <= 3:
                self.note_values[row][col] = new_note
                self.note_divides[row][col] = new_divide
                
                # ボタンテキストを更新
                self.update_button_text(row, col, self.step_buttons[row][col])
                
                # WebSocketクライアントに通知
                if hasattr(self, 'websocket_server') and self.websocket_server:
                    def notify_clients():
                        try:
                            # ノート値更新通知
                            note_message = {
                                'type': 'note_update',
                                'row': row,
                                'col': col,
                                'note': new_note
                            }
                            
                            # 分割設定更新通知
                            divide_message = {
                                'type': 'divide_update',
                                'row': row,
                                'col': col,
                                'divide': new_divide
                            }
                            
                            # 両方の更新を送信
                            asyncio.run(self.websocket_server.send_to_all(note_message))
                            asyncio.run(self.websocket_server.send_to_all(divide_message))
                        except Exception as e:
                            print(f"WebSocketノート更新通知エラー: {e}")
                    
                    # 別スレッドで非同期処理を実行
                    threading.Thread(target=notify_clients, daemon=True).start()
                
                dialog.destroy()
            else:
                tk.messagebox.showerror("入力エラー", "有効な範囲で値を入力してください。\nノート: 0-127\n分割: 1-3")
        
        def on_cancel():
            dialog.destroy()
        
        ok_button = tk.Button(button_frame, text="OK", command=on_ok, width=10)
        ok_button.pack(side=tk.LEFT, padx=5)
        
        cancel_button = tk.Button(button_frame, text="キャンセル", command=on_cancel, width=10)
        cancel_button.pack(side=tk.LEFT, padx=5)
        
        # ダイアログが閉じられるまで待機
        dialog.wait_window()
    
    def update_button_text(self, row, col, button):
        """ボタンテキストをノート情報で更新する"""
        note_value = self.note_values[row][col]
        divide_value = self.note_divides[row][col]
        
        # ノート値をノート名に変換
        octave = (note_value // 12) - 1
        note_idx = note_value % 12
        note_letters = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        note_name = f"{note_letters[note_idx]}{octave}"
        
        # 分割設定に応じてボタンの色を変更
        if self.sequence[row][col]:  # アクティブなステップ
            if divide_value == 2:
                # 2連符（アクティブ）- 緑系の色
                button.config(text=note_name, bg="#6bc26b")
            elif divide_value == 3:
                # 3連符（アクティブ）- 青系の色
                button.config(text=note_name, bg="#6b9ec2")
            else:
                # 通常（アクティブ）
                button.config(text=note_name, bg=self.active_color)
        else:  # 非アクティブなステップ
            if divide_value == 2:
                # 2連符（非アクティブ）- 薄い緑系の色
                button.config(text=note_name, bg="#4a7a4a")
            elif divide_value == 3:
                # 3連符（非アクティブ）- 薄い青系の色
                button.config(text=note_name, bg="#4a6a7a")
            else:
                # 通常（非アクティブ）
                button.config(text=note_name, bg=self.inactive_color)
    
    def update_bpm(self, event=None):
        """BPMを更新する"""
        try:
            new_bpm = int(self.bpm_var.get())
            if 20 <= new_bpm <= 300:  # 妥当なBPM範囲
                self.bpm = new_bpm
        except ValueError:
            self.bpm_var.set(str(self.bpm))  # 無効な入力の場合は元の値に戻す
    
    def change_midi_port(self, selection):
        """MIDI出力ポートを変更する"""
        # 以前のポートがあれば閉じる
        if hasattr(self, 'output_port') and self.output_port is not None:
            try:
                self.output_port.close()
            except:
                pass
            self.output_port = None
        
        try:
            # 新しいポートを開く
            self.port_name = selection
            print(f"MIDI出力ポートを '{selection}' に変更します")
            
            # テスト接続
            self.output_port = mido.open_output(self.port_name)
            print(f"MIDI出力ポート '{selection}' に接続成功")
            
            # 各チャンネルに初期CC値を送信（接続テスト兼ねて）
            self.send_all_cc_values()
        except Exception as e:
            print(f"MIDIポートの変更中にエラーが発生しました: {e}")
            # エラーが発生した場合はNoneに設定
            self.port_name = None
            self.output_port = None
            
            # UIを更新
            self.port_var.set("ポートなし")
    
    def send_all_cc_values(self):
        """全チャンネルの全CCパラメータを送信（ポートの変更時やリセット時）"""
        if not self.port_name or not self.output_port:
            print("MIDI出力ポートが設定されていないため、CCパラメータを送信できません")
            return
            
        try:
            for track_idx, track in enumerate(self.track_names):
                channel = self.midi_channels[track_idx]
                for cc, value in self.cc_values[track].items():
                    cc_num = int(cc[2:])  # "cc1" -> 1
                    try:
                        msg = mido.Message('control_change', channel=channel, control=cc_num, value=value)
                        self.output_port.send(msg)
                        # 送信間隔を少し空ける（連続送信によるバッファオーバーフローを防止）
                        time.sleep(0.01)
                    except Exception as e:
                        print(f"CC送信エラー: {track} CH{channel+1} {cc}={value}: {e}")
                
                # ピッチベンド値も送信
                if track in self.pitch_bend_values:
                    try:
                        pitch = self.pitch_bend_values[track]
                        self.output_port.send(mido.Message('pitchwheel', channel=channel, pitch=pitch))
                        time.sleep(0.01)
                    except Exception as e:
                        print(f"ピッチベンド送信エラー: {track} CH{channel+1} 値={self.pitch_bend_values[track]}: {e}")
            
            print("全CCパラメータとピッチベンドを送信しました")
        except Exception as e:
            print(f"パラメータ一括送信中にエラーが発生しました: {e}")
            # エラーが起きた場合はポート接続をリセット
            if self.output_port:
                try:
                    self.output_port.close()
                except:
                    pass
                self.output_port = None
                
            self.port_name = None
            # UIを更新
            self.root.after(0, lambda: self.port_var.set("ポートなし"))
    
    def update_cc(self, track, cc, value):
        """CCパラメータを更新する"""
        cc_key = cc
        if not cc.startswith('cc'):
            cc_key = f'cc{cc}'
        
        # トラックのCC値が初期化されていない場合は初期化
        if track not in self.cc_values:
            self.cc_values[track] = {}
        
        # CC値を更新
        self.cc_values[track][cc_key] = value
        
        # MIDIポートが開いていればCCメッセージを送信
        if self.output_port:
            try:
                # トラックインデックスからMIDIチャンネルを取得
                track_idx = self.track_names.index(track)
                channel = self.midi_channels[track_idx]
                
                # CC番号を取得
                cc_num = int(cc_key.replace('cc', ''))
                
                # CCメッセージを送信
                self.output_port.send(mido.Message('control_change', channel=channel, control=cc_num, value=value))
                print(f"CC更新送信: CH{channel+1} {cc_key}={value}")
                
                # CCの種類によっては特別な処理が必要
                # サステインの場合
                if cc_num == 64:
                    self.set_sustain(track, cc_key, value)
            except Exception as e:
                print(f"CCメッセージの送信中にエラーが発生しました: {e}")
        
        # WebSocketクライアントに通知
        if hasattr(self, 'websocket_server') and self.websocket_server:
            def notify_clients():
                try:
                    # CC値更新通知
                    cc_message = {
                        'type': 'cc_update',
                        'track': track,
                        'cc': cc_key if cc_key.startswith('cc') else f'cc{cc_key}',
                        'value': value
                    }
                    asyncio.run(self.websocket_server.send_to_all(cc_message))
                except Exception as e:
                    print(f"WebSocket CC更新通知エラー: {e}")
            
            # 別スレッドで非同期処理を実行
            threading.Thread(target=notify_clients, daemon=True).start()
    
    def send_preset(self, preset):
        """全チャンネルにプリセット変更メッセージを送信する"""
        if not self.port_name:
            print("MIDIポートが設定されていないため、プリセットを送信できません")
            return
            
        # ポートがない場合は再接続を試みる
        if not self.output_port:
            try:
                self.output_port = mido.open_output(self.port_name)
                print(f"MIDI出力ポートに再接続しました: {self.port_name}")
            except Exception as e:
                print(f"MIDI出力ポートへの再接続に失敗しました: {e}")
                self.port_name = None
                self.root.after(0, lambda: self.port_var.set("ポートなし"))
                return
            
        try:
            # 各チャンネルにプリセットメッセージを送信
            for channel in self.midi_channels:
                try:
                    # プログラムチェンジでプリセットを読み込む
                    self.output_port.send(mido.Message('program_change', channel=channel, program=preset-1))
                    # 連続送信によるバッファオーバーフローを防止
                    time.sleep(0.01)
                except Exception as e:
                    print(f"チャンネル {channel+1} へのプリセット送信中にエラー: {e}")
            
            print(f"プリセット {preset} を全チャンネルに送信しました")
        except Exception as e:
            print(f"プリセットメッセージの送信中にエラーが発生しました: {e}")
            
            # エラーが起きた場合はポート接続をリセット
            if self.output_port:
                try:
                    self.output_port.close()
                except:
                    pass
                self.output_port = None
                
            self.port_name = None
            # UIを更新
            self.root.after(0, lambda: self.port_var.set("ポートなし"))
    
    def toggle_play(self):
        """再生/停止を切り替える"""
        self.is_playing = not self.is_playing
        
        if self.is_playing:
            self.play_button.config(text="停止")
            self.current_step = 0  # 最初のステップから開始
            
            # 現在のMIDIポートを確認
            if not self.port_name:
                print("MIDIポートが設定されていないため、音は出力されません")
                
            # 別スレッドでシーケンサーを実行
            self.play_thread = threading.Thread(target=self.play_sequence)
            self.play_thread.daemon = True
            self.play_thread.start()
        else:
            self.play_button.config(text="再生")
            # すべてのノートをオフにする
            try:
                if self.output_port:
                    # 全チャンネルのサステインをオフにする
                    for track_idx, track in enumerate(self.track_names):
                        channel = self.midi_channels[track_idx]
                        # サステインオフ
                        self.output_port.send(mido.Message('control_change', channel=channel, control=64, value=0))
                        time.sleep(0.01)
                        # ピッチベンドをリセット
                        self.output_port.send(mido.Message('pitchwheel', channel=channel, pitch=0))
                        time.sleep(0.01)
                        self.pitch_bend_values[track] = 0
                        if track in self.pitch_bend_sliders:
                            self.root.after(0, lambda s=self.pitch_bend_sliders[track]: s.set(0))
                    
                    # 安全のため、全ノートオフメッセージを送信
                    for channel in range(16):  # 全MIDIチャンネル
                        for note in range(0, 127):
                            try:
                                self.output_port.send(mido.Message('note_off', channel=channel, note=note))
                                # 大量のメッセージを短時間に送信しないよう
                                if note % 10 == 0:
                                    time.sleep(0.001)
                            except:
                                pass
                    
                    # 各トラックのアクティブノートをクリア
                    for track in self.track_names:
                        self.active_notes[track].clear()
                        self.sustain_active[track] = False
                
            except Exception as e:
                print(f"ノートオフメッセージの送信中にエラーが発生しました: {e}")
                
                # エラーが起きた場合はポートを閉じるが、名前は保持する
                if self.output_port:
                    try:
                        self.output_port.close()
                    except:
                        pass
                    self.output_port = None
                    print(f"ポートを閉じましたが、設定は保持します: {self.port_name}")
        
        # WebSocketサーバーを通じてクライアントに通知
        if hasattr(self, 'websocket_server') and self.websocket_server:
            # 非同期関数を同期的に呼び出すためのラッパー
            def notify_clients():
                try:
                    asyncio.run(self.websocket_server.send_to_all({
                        'type': 'play_state',
                        'is_playing': self.is_playing,
                        'current_step': self.current_step
                    }))
                except AttributeError:
                    print("WebSocketサーバーにsend_to_all属性がありません")
                except Exception as e:
                    print(f"通知エラー: {e}")
            
            # 別スレッドで通知を送信
            threading.Thread(target=notify_clients, daemon=True).start()
    
    def play_sequence(self):
        """シーケンスを再生する"""
        step_time = 60.0 / self.bpm / 4  # 16分音符の長さ（基本単位）
        
        # ポートを一度だけ開く
        try:
            if self.port_name:
                # すでにポートがオープンしている場合は閉じる
                if self.output_port:
                    try:
                        self.output_port.close()
                    except:
                        pass
                
                self.output_port = mido.open_output(self.port_name)
                print(f"シーケンサーがMIDIポート '{self.port_name}' を開きました")
                
                # 再生開始時に全チャンネルのサステインをリセット（オフに）
                for track_idx, track in enumerate(self.track_names):
                    channel = self.midi_channels[track_idx]
                    self.output_port.send(mido.Message('control_change', channel=channel, control=64, value=0))
                    self.sustain_active[track] = False
                    self.active_notes[track].clear()
                    time.sleep(0.01)  # 連続送信を防ぐための短い待機
            
            else:
                print("MIDIポートが設定されていないため、音は出力されません")
        except Exception as e:
            print(f"MIDIポートを開く際にエラーが発生しました: {e}")
            self.is_playing = False
            self.root.after(0, lambda: self.play_button.config(text="再生"))
            # ポートオブジェクトのみクリアし、ポート名は保持
            self.output_port = None
            print(f"ポートを開けませんでしたが、設定は保持します: {self.port_name}")
            return
        
        try:
            # 次のステップに進むまでの残り時間を計測するための変数
            last_step_time = time.time()
            last_notification_time = 0  # WebSocket通知の最後の時間
            notification_interval = 0.03  # 通知間隔（30ms - 非常に頻繁に更新）
            
            while self.is_playing:
                current_time = time.time()
                elapsed_since_last_step = current_time - last_step_time
                
                # 現在のステップを強調表示（GUIスレッドで実行）
                self.root.after(0, lambda s=self.current_step: self.highlight_step(s))
                
                # WebSocket通知の送信（一定間隔で）
                if (current_time - last_notification_time) >= notification_interval:
                    # 非同期関数を同期的に呼び出すためのラッパー（別スレッドで実行）
                    if hasattr(self, 'websocket_server') and self.websocket_server:
                        try:
                            # ステップの更新通知だけを送信
                            threading.Thread(target=lambda: asyncio.run(
                                self.websocket_server.send_to_all({
                                    'type': 'current_step',
                                    'step': self.current_step
                                })
                            ), daemon=True).start()
                            last_notification_time = current_time
                        except Exception as e:
                            print(f"WebSocket通知エラー: {e}")
                
                # 現在のステップのノートを再生
                if self.output_port:
                    for track in range(self.tracks):
                        if self.sequence[track][self.current_step]:
                            # 各ステップの設定されたノート値とノート分割を使用
                            channel = self.midi_channels[track]
                            note = self.note_values[track][self.current_step]
                            note_divide = self.note_divides[track][self.current_step]
                            track_name = self.track_names[track]
                            
                            # 分割設定に基づいて処理
                            if note_divide == 2:  # 2連符
                                divisions = 2
                            elif note_divide == 3:  # 3連符
                                divisions = 3
                            else:  # 通常の16分音符（分割なし）
                                divisions = 1
                            
                            # 分割に応じた音符の長さと間隔
                            division_duration = step_time / divisions
                            
                            # 連符の各音を再生
                            for i in range(divisions):
                                # ノートオンメッセージを送信
                                try:
                                    self.output_port.send(mido.Message('note_on', channel=channel, note=note, velocity=100))
                                    print(f"ノートオン: CH{channel+1} ノート={note} 分割={i+1}/{divisions}")
                                    
                                    # サステインがアクティブな場合、ノートを追跡リストに追加
                                    if self.sustain_active[track_name]:
                                        self.active_notes[track_name].add(note)
                                    
                                    # 一定時間後にノートオフを送信（サステインがオフの場合のみ）
                                    if not self.sustain_active[track_name]:
                                        # 音符の長さは分割数に応じて短くする（division_duration / 2）
                                        note_off_time = division_duration * 0.8  # 音の持続時間（少し短めに）
                                        time.sleep(note_off_time)
                                        self.output_port.send(mido.Message('note_off', channel=channel, note=note))
                                        print(f"ノートオフ: CH{channel+1} ノート={note}")
                                    
                                    # 次の分割音までの間隔を空ける（最後の音の場合は不要）
                                    if i < divisions - 1:
                                        # 次の連符音までの間隔
                                        gap_time = division_duration - note_off_time
                                        if gap_time > 0:
                                            time.sleep(gap_time)
                                
                                except Exception as e:
                                    print(f"ノート再生中にエラー: {e}")
                
                # この時点での経過時間を計算
                current_time = time.time()
                total_elapsed = current_time - last_step_time
                
                # 次のステップまでの残り時間を待機
                remaining_time = step_time - total_elapsed
                if remaining_time > 0:
                    time.sleep(remaining_time)
                
                # 次のステップの時間を記録
                last_step_time = time.time()
                
                # 次のステップへ
                self.current_step = (self.current_step + 1) % self.steps
                
        except Exception as e:
            print(f"シーケンス再生中にエラーが発生しました: {e}")
            self.is_playing = False
            self.root.after(0, lambda: self.play_button.config(text="再生"))
        finally:
            # すべてのノートオフを送信して終了
            if self.output_port:
                try:
                    for channel in range(16):
                        for note in range(128):
                            self.output_port.send(mido.Message('note_off', channel=channel, note=note))
                except Exception as e:
                    print(f"ノートオフ送信中にエラーが発生しました: {e}")
    
    def highlight_step(self, step):
        """ステップを強調表示する"""
        # すべてのステップインジケーターの色をリセット
        for indicator in self.step_indicators:
            indicator.config(bg="lightgray")
        
        # 現在のステップを強調表示
        if step < len(self.step_indicators):
            self.step_indicators[step].config(bg="orange")
            
        # WebSocketサーバーのnotify_stepメソッドを使用
        if hasattr(self, 'websocket_server') and self.websocket_server:
            # このメソッドは複雑なスレッド処理を回避するため非推奨
            pass
    
    def change_midi_input_port(self, selection):
        """MIDI入力ポートを変更する"""
        try:
            # 現在のポートを閉じる
            if self.input_port:
                self.input_port.close()
                self.input_port = None
            
            # 「なし」が選択された場合
            if selection == "なし":
                self.input_port_name = None
                return
            
            # 新しいポートを開く
            self.input_port_name = selection
            self.input_port = mido.open_input(self.input_port_name, callback=self.handle_midi_input)
            print(f"MIDI入力ポート '{selection}' を開きました")
        except Exception as e:
            print(f"MIDI入力ポートの変更中にエラーが発生しました: {e}")
            self.input_port_name = None
            self.input_port_var.set("なし")
    
    def toggle_midi_clock(self):
        """MIDI Clock同期の有効/無効を切り替える"""
        self.midi_clock_enabled = self.clock_var.get()
        if self.midi_clock_enabled:
            print("MIDI Clock同期を有効にしました")
            # カウンタをリセット
            self.last_clock_time = None
            self.clock_count = 0
        else:
            print("MIDI Clock同期を無効にしました")
    
    def handle_midi_input(self, message):
        """MIDI入力メッセージを処理する"""
        # MIDI Clockメッセージ (タイミングクロック)
        if message.type == 'clock' and self.midi_clock_enabled:
            self.process_midi_clock()
        
        # Start, Continue, Stopメッセージ
        elif message.type == 'start' or message.type == 'continue':
            if not self.is_playing:
                self.toggle_play()
        elif message.type == 'stop':
            if self.is_playing:
                self.toggle_play()
    
    def process_midi_clock(self):
        """MIDI Clockメッセージを処理してBPMを計算する"""
        current_time = time.time()
        
        # 最初のクロックメッセージの場合
        if self.last_clock_time is None:
            self.last_clock_time = current_time
            self.clock_count = 1
            return
        
        # クロックカウントを増やす
        self.clock_count += 1
        
        # 24クロックで1拍 (MIDI規格)
        if self.clock_count >= 24:
            # 24クロック分の時間からBPMを計算
            elapsed_time = current_time - self.last_clock_time
            if elapsed_time > 0:
                # BPM = 60秒 / 1拍の秒数
                new_bpm = int(60 / elapsed_time)
                
                # 妥当なBPM範囲内であれば更新
                if 20 <= new_bpm <= 300:
                    self.bpm = new_bpm
                    # UIを更新 (スレッドセーフに)
                    self.root.after(0, lambda: self.bpm_var.set(str(self.bpm)))
            
            # カウンタをリセット
            self.last_clock_time = current_time
            self.clock_count = 0

    def set_sustain(self, track, cc, value):
        """サステインの値を設定する（CC64）"""
        old_value = self.cc_values[track].get(cc, 0)
        
        # 値が変わらない場合は何もしない
        if old_value == value:
            return
            
        print(f"サステイン設定: {track} {cc}={value}")
        
        # サステイン状態を更新
        channel = self.midi_channels[self.track_names.index(track)]
        self.sustain_active[track] = (value >= 64)
        
        # サステイン値を保存
        self.cc_values[track][cc] = value
        
        # サステインをOFFにする場合、鳴っていた音を全て止める
        if not self.sustain_active[track] and self.active_notes[track]:
            if self.output_port:
                try:
                    # まずサステインOFFのCC64を送信
                    self.output_port.send(mido.Message('control_change', channel=channel, control=64, value=0))
                    time.sleep(0.01)  # 少し待機して処理を確実に
                    
                    # 保留中の全てのノートをオフ
                    for note in list(self.active_notes[track]):
                        try:
                            self.output_port.send(mido.Message('note_off', channel=channel, note=note))
                            time.sleep(0.001)  # 連続送信のため少し待機
                        except Exception as e:
                            print(f"ノートオフ送信中にエラー: {e}")
                    
                    # サステインをオフにしたらノートリストをクリア
                    self.active_notes[track].clear()
                    
                except Exception as e:
                    print(f"サステイン解除中にエラー: {e}")
        
        # CCメッセージとしてMIDIに送信
        self.update_cc(track, cc, value)
    
    def show_mgb_info(self):
        """mGB MIDIインプリメンテーション情報を表示する"""
        info_window = tk.Toplevel(self.root)
        info_window.title("mGB MIDIインプリメンテーション情報")
        info_window.geometry("600x500")
        
        # 情報テキスト
        info_text = """
mGB MIDIインプリメンテーション情報

mGBはGameboy用MIDIサウンドモジュールプログラムです。
以下の5つのチャンネルをサポートしています：

1. PU1 - MIDIチャンネル1
   - Program Change: 1-15
   - Pitch Bend: ±12
   - CC1: Pulse Width (0,32,64,127)
   - CC2: Envelope mode (0-127)
   - CC3: Pitch Sweep
   - CC4: Pitch Bend Range (0-48)
   - CC10: Pan
   - CC64: Sustain (<64=OFF, >63=ON)

2. PU2 - MIDIチャンネル2
   - Program Change: 1-15
   - Pitch Bend: ±12
   - CC1: Pulse Width (0,32,64,127)
   - CC2: Envelope mode (0-127)
   - CC4: PB Range (0-48)
   - CC10: Pan
   - CC64: Sustain (<64=OFF, >63=ON)

3. WAV - MIDIチャンネル3
   - Program Change: 1-15
   - Pitch Bend: ±12
   - CC1: Shape select (0-127)
   - CC2: Shape offset (0-127)
   - CC3: Pitch Sweep speed (0=OFF, 1-127)
   - CC4: Pitch Bend Range
   - CC10: Pan
   - CC64: Sustain (<64=OFF, >63=ON)

4. NOISE - MIDIチャンネル4
   - Program Change: 1-15
   - Pitch Bend: ±24
   - CC2: Envelope mode (0-127)
   - CC10: Pan
   - CC64: Sustain (<64=OFF, >63=ON)

5. POLY MODE - MIDIチャンネル5
   - Program Change: 1-15
   - Pitch Bend: ±2
   - CC1: See PU1 CC1
   - CC10: Pan
   - CC64: Sustain (<64=OFF, >63=ON)
   
詳細情報：https://github.com/trash80/mGB
        """
        
        text_widget = tk.Text(info_window, wrap=tk.WORD)
        text_widget.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        text_widget.insert(tk.END, info_text)
        text_widget.config(state=tk.DISABLED)
        
        # スクロールバー
        scrollbar = tk.Scrollbar(text_widget)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=text_widget.yview)
        
        # 閉じるボタン
        close_button = tk.Button(info_window, text="閉じる", command=info_window.destroy)
        close_button.pack(pady=10)

    def start_websocket_server(self):
        """
        WebSocketサーバーを起動する（新しいアーキテクチャに移行済み）
        このメソッドは後方互換性のためだけに存在しています。
        """
        pass  # 新しいアーキテクチャでは別モジュールで実装

    def reset_pitch_bend(self, track):
        """ピッチベンドをリセット（0）に戻す"""
        self.update_pitch_bend(track, 0)
    
    def update_pitch_bend(self, track, value):
        """ピッチベンドの値を更新してMIDIメッセージを送信する"""
        if value < -8192 or value > 8191:
            print(f"無効なピッチベンド値: {value}")
            return
            
        try:
            self.pitch_bend_values[track] = value
            
            if not self.port_name or not self.output_port:
                return
                
            channel = self.midi_channels[self.track_names.index(track)]
            
            # PBレンジに合わせてピッチベンド値を適用
            pb_range = self.cc_values[track].get("cc4", 2)
            # スケーリングは行わず、単純にmidoライブラリに任せる
            
            try:
                msg = mido.Message('pitchwheel', channel=channel, pitch=value)
                self.output_port.send(msg)
                print(f"ピッチベンド送信: CH{channel+1} 値={value} PBレンジ={pb_range}")
            except Exception as e:
                print(f"ピッチベンドメッセージの送信中にエラー: {e}")
                # エラーが起きた場合は再接続を試みる
                try:
                    if self.output_port:
                        self.output_port.close()
                    self.output_port = mido.open_output(self.port_name)
                    self.output_port.send(mido.Message('pitchwheel', channel=channel, pitch=value))
                    print(f"ポート再接続後にピッチベンド送信成功: CH{channel+1} 値={value}")
                except Exception as e2:
                    print(f"再接続後もピッチベンドメッセージの送信に失敗: {e2}")
                    self.port_name = None
                    self.output_port = None
                    self.root.after(0, lambda: self.port_var.set("ポートなし"))
        except Exception as e:
            print(f"ピッチベンドの更新中にエラー: {e}")
            
    def set_pulse_width(self, track, cc, value, slider, cc_var):
        """パルス幅プリセットボタンのためのヘルパーメソッド"""
        # 値を更新
        cc_var.set(value)
        slider.set(value)
        # CCメッセージとしてMIDIに送信
        self.update_cc(track, cc, value)

    def update_clock_divide(self, selection):
        """クロックディバイドを更新する"""
        try:
            self.clock_divide = int(selection)
            print(f"クロックディバイドを{selection}に設定しました")
        except ValueError:
            self.clock_divide = 1
            print("クロックディバイドをデフォルト値(1)に設定しました")
        
        # WebSocketサーバーを通じてクライアントに通知
        if hasattr(self, 'websocket_server') and self.websocket_server:
            def notify_clients():
                asyncio.run(self.websocket_server.send_state())
            threading.Thread(target=notify_clients, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = MidiSequencer(root)
    
    # アプリケーション終了時の処理
    def on_closing():
        print("アプリケーションを終了します...")
        if app.is_playing:
            app.toggle_play()  # 再生を停止
        
        # MIDIポートを確実に閉じる
        if app.output_port:
            try:
                # 念のため全チャンネルにAll Sound Off（CC 120）を送信
                for channel in range(16):
                    try:
                        app.output_port.send(mido.Message('control_change', channel=channel, control=120, value=0))
                    except:
                        pass
                
                # ポートを閉じる
                app.output_port.close()
                print("MIDI出力ポートを閉じました")
            except Exception as e:
                print(f"MIDI出力ポート終了時にエラー: {e}")
            
        # 入力ポートを閉じる
        if app.input_port:
            try:
                app.input_port.close()
                print("MIDI入力ポートを閉じました")
            except Exception as e:
                print(f"MIDI入力ポート終了時にエラー: {e}")
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop() 