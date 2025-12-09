import threading
import time
import requests
import base64
import os
import logging
import traceback
import whisper
import torch
import json
import queue # Dùng để đẩy dữ liệu ra Frontend

import config

logger = logging.getLogger(__name__)

class AudioAutomationBot:
    def __init__(self, search_system):
        self.search_system = search_system
        self.is_running = False
        self.thread = None
        self.whisper_model = None
        self.msg_queue = queue.Queue() # Hàng đợi tin nhắn cho SSE
        
        # Runtime config
        self.session_id = None
        self.evaluation_id = None
        self.last_task_id = None
        self.api_base = f"{config.EVAL_SERVER_URL}/api/v2"

    def load_model(self):
        """Load model chỉ khi cần thiết"""
        if self.whisper_model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.push_update("system", f"Loading Whisper model on {device}...")
            try:
                self.whisper_model = whisper.load_model("base", device=device)
                self.push_update("system", "Whisper loaded successfully.")
            except Exception as e:
                self.push_update("error", f"Load Whisper failed: {str(e)}")
                raise e

    def push_update(self, event_type, data):
        """Đẩy dữ liệu vào hàng đợi để gửi xuống Client"""
        message = {
            "type": event_type, # 'log', 'result', 'transcript'
            "data": data,
            "timestamp": time.time()
        }
        self.msg_queue.put(message)

    def start_loop(self, session_id, evaluation_id):
        if self.is_running: return
        
        self.session_id = session_id
        self.evaluation_id = evaluation_id
        self.is_running = True
        
        # Load model trong thread riêng để không block request
        self.thread = threading.Thread(target=self._run_process, daemon=True)
        self.thread.start()

    def stop_loop(self):
        self.is_running = False
        self.push_update("system", "Automation stopped.")

    def _run_process(self):
        try:
            self.load_model()
            self.push_update("system", "Polling loop started...")
            
            while self.is_running:
                try:
                    self._check_dres_status()
                except Exception as e:
                    logger.error(f"Loop Error: {e}")
                
                time.sleep(1) # Poll mỗi 1 giây
        except Exception as e:
            self.push_update("error", f"Fatal Error: {str(e)}")
            self.is_running = False

    def _check_dres_status(self):
        # 1. Lấy trạng thái
        url = f"{self.api_base}/evaluation/{self.evaluation_id}/state"
        cookies = {'SESSIONID': self.session_id}
        try:
            res = requests.get(url, cookies=cookies, timeout=3, verify=False)
            if res.status_code != 200: return
            
            state = res.json()
            if state.get('evaluationStatus') != 'ACTIVE': return
            
            task_status = state.get('taskStatus')
            current_task_id = state.get('taskTemplateId')

            # 2. Nếu có Task mới -> Xử lý
            if task_status == 'RUNNING' and current_task_id and current_task_id != self.last_task_id:
                self.last_task_id = current_task_id
                self.push_update("system", f"New Task Detected: {current_task_id}")
                self._process_hint(current_task_id)

        except Exception as e:
            logger.error(f"Polling check failed: {e}")

    def _process_hint(self, task_id):
        url = f"{self.api_base}/evaluation/{self.evaluation_id}/template/task/{task_id}/hint"
        cookies = {'SESSIONID': self.session_id}
        try:
            res = requests.get(url, cookies=cookies, timeout=10, verify=False)
            if res.status_code != 200: return
            
            data = res.json()
            for element in data.get('sequence', []):
                if element.get('contentType') == 'VIDEO':
                    # Có video hint -> Tải về và xử lý
                    self._handle_video_content(task_id, element.get('content'))
                    break # Chỉ lấy video đầu tiên
        except Exception as e:
            logger.error(f"Get hint failed: {e}")

    def _handle_video_content(self, task_id, b64_content):
        filename = f"temp_hint_{task_id}.mp4"
        try:
            # 1. Lưu file
            with open(filename, "wb") as f:
                f.write(base64.b64decode(b64_content))
            
            # 2. Transcribe
            self.push_update("system", "Transcribing video...")
            result = self.whisper_model.transcribe(filename)
            text = result['text'].strip()
            
            if text:
                # Gửi text xuống frontend để điền vào ô input
                self.push_update("transcript", text)
                
                # 3. Thực hiện Search Audio ngay lập tức
                self.push_update("system", f"Searching for: {text}")
                results = self.search_system.transcript_search(text, max_results=100)
                
                # Gửi kết quả search xuống frontend để hiển thị
                self.push_update("search_results", results)
            else:
                self.push_update("system", "No speech detected in hint.")
                
        except Exception as e:
            self.push_update("error", f"Processing video failed: {e}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)

    def event_stream(self):
        """Generator function cho SSE"""
        while True:
            try:
                # Chờ tin nhắn mới trong queue (timeout 1s để check is_running)
                msg = self.msg_queue.get(timeout=1)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                # Giữ kết nối
                yield ": keep-alive\n\n"
