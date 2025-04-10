import sys
import os
import re
import json
import time
import threading
import requests
import qrcode
from io import BytesIO
from PIL import Image
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, 
                           QProgressBar, QFileDialog, QFrame, QMessageBox, QTabWidget, QDialog,
                           QMenuBar, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl, QEventLoop
from PyQt6.QtGui import QPixmap, QIcon, QDesktopServices, QColor, QPalette
# 当前版本号
CURRENT_VERSION = '1.0.0'

class VersionChecker(QThread):
    version_available = pyqtSignal(str, str)  # 参数：新版本号，下载链接
    check_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.github_api_url = 'https://api.github.com/repos/WatererQuan/BiliDown-GUI/releases/latest'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def run(self):
        try:
            # 获取GitHub最新release信息
            response = requests.get(self.github_api_url, headers=self.headers, timeout=10)
            if response.status_code == 403:
                self.check_error.emit('检查更新失败：GitHub API访问受限，请稍后再试')
                return
            elif response.status_code != 200:
                self.check_error.emit(f'检查更新失败：GitHub服务器返回状态码 {response.status_code}')
                return
            
            data = response.json()
            latest_version = data['tag_name'].lstrip('v')  # 移除版本号前的'v'前缀
            download_url = data['html_url']
            
            # 比较版本号
            if self._compare_versions(latest_version, CURRENT_VERSION) > 0:
                self.version_available.emit(latest_version, download_url)
        
        except Exception as e:
            self.check_error.emit(f'检查更新失败：{str(e)}')
    
    def _compare_versions(self, version1, version2):
        """比较两个版本号，返回：1 如果version1更新，0 如果相同，-1 如果version2更新"""
        def parse_version(version):
            # 处理版本号，分离数字部分和后缀部分
            parts = version.split('-')
            version_nums = parts[0].split('.')
            suffix = parts[1] if len(parts) > 1 else ''
            
            # 转换版本号为整数列表
            try:
                nums = [int(x) for x in version_nums]
            except ValueError:
                return None, suffix
            
            return nums, suffix
        
        # 解析两个版本号
        v1_nums, v1_suffix = parse_version(version1)
        v2_nums, v2_suffix = parse_version(version2)
        
        # 如果版本号解析失败，返回0
        if v1_nums is None or v2_nums is None:
            return 0
        
        # 比较版本号数字部分
        for i in range(max(len(v1_nums), len(v2_nums))):
            v1 = v1_nums[i] if i < len(v1_nums) else 0
            v2 = v2_nums[i] if i < len(v2_nums) else 0
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
        
        # 如果数字部分相同，比较后缀
        # beta版本视为比无后缀版本旧
        if v1_suffix == v2_suffix:
            return 0
        elif v1_suffix == 'beta':
            return -1
        elif v2_suffix == 'beta':
            return 1
        
        return 0

def show_update_dialog(parent, new_version, download_url):
    """显示更新提示对话框"""
    msg = QMessageBox(parent)
    msg.setWindowTitle('发现新版本')
    msg.setText(f'发现新版本 v{new_version}\n是否前往下载？')
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    
    if msg.exec() == QMessageBox.StandardButton.Yes:
        QDesktopServices.openUrl(QUrl(download_url))

class LoginThread(QThread):
    login_success = pyqtSignal(dict)
    login_failed = pyqtSignal(str)
    qrcode_ready = pyqtSignal(QPixmap)
    status_update = pyqtSignal(str)
    
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.cancel = False
    
    def run(self):
        try:
            # 获取二维码
            qr_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            response = self.session.get(qr_url)
            if response.status_code != 200:
                self.login_failed.emit("获取二维码失败：服务器无响应")
                return
            
            data = response.json()
            if data.get('code') != 0:
                self.login_failed.emit(f"获取二维码失败：{data.get('message', '未知错误')}")
                return

            qrcode_key = data['data']['qrcode_key']
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data['data']['url'])
            
            # 生成二维码图片
            qr_image = qr.make_image(fill_color="black", back_color="white")
            bio = BytesIO()
            qr_image.save(bio, format='PNG')
            bio.seek(0)
            
            # 发送二维码图片
            pixmap = QPixmap()
            pixmap.loadFromData(bio.getvalue())
            self.qrcode_ready.emit(pixmap)
            
            # 检查登录状态
            while not self.cancel:
                try:
                    check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
                    params = {'qrcode_key': qrcode_key}
                    response = self.session.get(check_url, params=params)
                    
                    if response.status_code != 200 or not response.content:
                        self.login_failed.emit("服务器响应异常")
                        return
                        
                    data = response.json()
                    
                    if data['code'] == 0:
                        if data['data']['code'] == 0:  # 登录成功
                            # 获取用户信息
                            nav_response = self.session.get('https://api.bilibili.com/x/web-interface/nav')
                            nav_data = nav_response.json()
                            self.login_success.emit(nav_data)
                            return
                        elif data['data']['code'] == 86038:  # 二维码过期
                            self.status_update.emit("二维码已过期，请重新扫码")
                            return
                        elif data['data']['code'] == 86090:  # 已扫码未确认
                            self.status_update.emit("已扫码，请在APP确认登录")
                    else:
                        self.login_failed.emit(f"登录失败：{data.get('message', '未知错误')}")
                        return
                        
                    # 每1秒轮询一次
                    time.sleep(1)
                    
                except Exception as e:
                    self.login_failed.emit(f"登录检查失败：{str(e)}")
                    return
                    
        except Exception as e:
            self.login_failed.emit(f"登录过程出错：{str(e)}")

class DownloadThread(QThread):
    progress_update = pyqtSignal(int, int)
    speed_update = pyqtSignal(float)
    status_update = pyqtSignal(str)
    download_complete = pyqtSignal()
    download_error = pyqtSignal(str)
    
    def __init__(self, session, bvid, cid, quality, download_path, options, api_type):
        super().__init__()
        self.session = session
        self.bvid = bvid
        self.cid = cid
        self.quality = quality
        self.download_path = download_path
        self.options = options  # 字典，包含video, audio, subtitle, cover
        self.api_type = api_type
        self.downloading = False
        self.paused = False
        self.cancel = False
    
    def run(self):
        try:
            self.downloading = True
            self.status_update.emit("获取视频信息...")
            
            # 获取视频信息
            video_info = self.get_video_info()
            
            # 如果已经取消，则直接返回
            if self.cancel:
                self.status_update.emit("下载已取消")
                self.download_complete.emit()
                return
            
            # 设置文件名
            base_name = f"{video_info['title']}"
            if len(video_info['pages']) > 1:
                current_page = next((p for p in video_info['pages'] if p['cid'] == self.cid), None)
                if current_page:
                    base_name += f"_P{current_page['page']}_{current_page['part']}"
            
            # 创建下载目录
            os.makedirs(self.download_path, exist_ok=True)
            
            # 下载封面
            if self.options.get('cover', False):
                self.status_update.emit("下载封面...")
                cover_url = video_info.get('pic', '')
                if cover_url:
                    cover_path = os.path.join(self.download_path, f"{base_name}.jpg")
                    self.download_file(cover_url, cover_path)
            
            # 字幕下载功能待开发
            if self.options.get('subtitle', False):
                self.status_update.emit("字幕下载功能待开发")
            
            # 获取下载地址
            self.status_update.emit("获取下载地址...")
            download_info = self.get_download_url()
            
            # 下载视频和音频
            if 'dash' in download_info:
                if self.options.get('video', False) or self.options.get('audio', False):
                    video_path = os.path.join(self.download_path, f"{base_name}.mp4")
                    
                    if self.options.get('video', False) and self.options.get('audio', False):
                        temp_video = video_path + '.video.mp4'
                        temp_audio = video_path + '.audio.m4a'
                        
                        self.status_update.emit("下载视频流...")
                        self.download_stream(download_info['dash']['video'][0]['baseUrl'], temp_video)
                        
                        if self.cancel:
                            return
                        
                        self.status_update.emit("下载音频流...")
                        self.download_stream(download_info['dash']['audio'][0]['baseUrl'], temp_audio)
                        
                        if self.cancel:
                            return
                        
                        self.status_update.emit("合并音视频...")
                        self.merge_video_audio(temp_video, temp_audio, video_path)
                        
                        # 删除临时文件
                        try:
                            os.remove(temp_video)
                            os.remove(temp_audio)
                        except:
                            pass
                    elif self.options.get('video', False):
                        self.status_update.emit("下载视频流...")
                        self.download_stream(download_info['dash']['video'][0]['baseUrl'], video_path)
                    elif self.options.get('audio', False):
                        audio_path = os.path.join(self.download_path, f"{base_name}.m4a")
                        self.status_update.emit("下载音频流...")
                        self.download_stream(download_info['dash']['audio'][0]['baseUrl'], audio_path)
            
            if not self.cancel:
                self.status_update.emit("下载完成！")
                self.download_complete.emit()
            
        except Exception as e:
            self.download_error.emit(f"下载失败：{str(e)}")
        finally:
            self.downloading = False
    
    def get_video_info(self):
        url = f"https://api.bilibili.com/x/web-interface/view"
        params = {'bvid': self.bvid}
        response = self.session.get(url, params=params)
        data = response.json()
        if data.get('code') != 0:
            raise Exception(f"获取视频信息失败：{data.get('message', '未知错误')}")
        return data['data']
    
    def get_download_url(self):
        if self.api_type == "官方":
            url = f"https://api.bilibili.com/x/player/playurl"
            params = {
                'bvid': self.bvid,
                'cid': self.cid,
                'qn': self.quality,
                'fnval': 4048,  # 增加fnval值以支持更多格式
                'fnver': 0,
                'fourk': 1,
                'platform': 'pc',
                'high_quality': 1,
                'otype': 'json',
                'dolby': 1,  # 支持杜比视界
                'hdr': 1,     # 支持HDR
                '8k': 1       # 支持8K
            }
            headers = {
                'Referer': f'https://www.bilibili.com/video/{self.bvid}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Origin': 'https://www.bilibili.com',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Range': 'bytes=0-'
            }
            response = self.session.get(url, params=params, headers=headers)
            data = response.json()
            if data.get('code') != 0:
                raise Exception(f"获取下载地址失败：{data.get('message', '未知错误')}")
            return data['data']
        else:
            # 第三方接口实现
            api_type = self.api_type
            
            try:
                if api_type == "解析接口1":
                    api_url = f"https://api.injahow.cn/bparse/?bv={self.bvid}&p=1&format=mp4&quality={self.quality}"
                elif api_type == "RapidAPI":
                    api_url = f"https://bilibili-video-api.p.rapidapi.com/video/{self.bvid}"
                    headers = {
                        'X-RapidAPI-Key': '在此填入你的RapidAPI密钥',
                        'X-RapidAPI-Host': 'bilibili-video-api.p.rapidapi.com'
                    }
                elif api_type == "BiliAPI":
                    api_url = f"https://bili-api.vercel.app/video/{self.bvid}"
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': f'https://www.bilibili.com/video/{self.bvid}'
                }
                
                if api_type == "解析接口1":
                    response = requests.get(api_url, headers=headers, verify=True)
                    data = response.json()
                    video_url = data.get('url', '')
                elif api_type in ["RapidAPI", "BiliAPI"]:
                    response = requests.get(api_url, headers=headers, verify=True)
                    data = response.json()
                    video_url = data.get('data', {}).get('playurl', '')
                
                if not video_url:
                    raise Exception("无法获取视频地址")
                
                return {
                    'durl': [{
                        'url': video_url
                    }]
                }
            except Exception as e:
                raise Exception(f"第三方接口解析失败：{str(e)}")
    
    def download_stream(self, url, filename):
        headers = {
            'Referer': 'https://www.bilibili.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Range': 'bytes=0-'
        }
        
        response = self.session.get(url, stream=True, headers=headers)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 * 1024  # 1MB块大小
        
        # 立即发送总大小信息，确保UI显示总文件大小
        self.progress_update.emit(0, total_size)
        # 确保目录存在
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        downloaded_size = 0
        last_update_time = time.time()
        last_downloaded_size = 0
        
        try:
            with open(filename, 'wb') as f:
                for data in response.iter_content(block_size):
                    if self.cancel:  # 检查是否取消下载
                        return
                    
                    while self.paused:  # 暂停下载
                        time.sleep(0.1)
                        if self.cancel:  # 在暂停时检查是否取消
                            return
                    
                    if data:  # 确保数据不为空
                        downloaded_size += len(data)
                        f.write(data)
                        
                        # 更新进度
                        self.progress_update.emit(downloaded_size, total_size)
                        
                        # 计算下载速度
                        current_time = time.time()
                        if current_time - last_update_time >= 1.0:  # 每秒更新一次速度
                            speed = (downloaded_size - last_downloaded_size) / (current_time - last_update_time)
                            self.speed_update.emit(speed)
                            
                            last_update_time = current_time
                            last_downloaded_size = downloaded_size
        except Exception as e:
            if not self.cancel:
                raise e
    
    def download_file(self, url, filename):
        try:
            # 详细记录下载信息
            self.status_update.emit(f"正在下载: {url}")
            self.status_update.emit(f"保存到: {filename}")
            
            # 确保下载路径存在
            try:
                dir_path = os.path.dirname(filename)
                self.status_update.emit(f"创建目录: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
                
                # 验证目录是否成功创建
                if not os.path.exists(dir_path):
                    raise Exception(f"无法创建目录: {dir_path}")
            except Exception as e:
                self.status_update.emit(f"创建目录失败: {str(e)}")
                raise Exception(f"创建保存目录失败: {str(e)}")
            
            # 下载文件
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com'
            }
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"下载失败，状态码：{response.status_code}")
                
            # 检查内容是否为JSON格式（针对字幕）
            if url.endswith('.json') or 'subtitle_url' in url:
                try:
                    # 尝试解析JSON
                    subtitle_data = response.json()
                    self.status_update.emit(f"字幕数据解析成功，开始转换格式...")
                    
                    # 转换为SRT格式
                    srt_content = self.convert_subtitle_to_srt(subtitle_data)
                    
                    # 使用utf-8编码保存字幕文件
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(srt_content)
                        
                        # 验证文件是否成功保存
                        if os.path.exists(filename):
                            self.status_update.emit(f"字幕已成功保存到: {filename}")
                        else:
                            raise Exception(f"文件写入后未找到: {filename}")
                        return
                    except Exception as e:
                        self.status_update.emit(f"字幕文件写入失败: {str(e)}")
                        raise Exception(f"字幕文件写入失败: {str(e)}")
                except json.JSONDecodeError as e:
                    self.status_update.emit(f"字幕JSON解析失败：{str(e)}，原始内容：{response.text[:200]}")
                    raise Exception(f"字幕JSON解析失败：{str(e)}")
                except Exception as e:
                    self.status_update.emit(f"字幕处理失败：{str(e)}")
                    raise Exception(f"字幕处理失败：{str(e)}")
            
            # 保存普通文件
            try:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                
                # 验证文件是否成功保存
                if os.path.exists(filename):
                    self.status_update.emit(f"文件已成功保存到: {filename}")
                else:
                    raise Exception(f"文件写入后未找到: {filename}")
            except Exception as e:
                self.status_update.emit(f"文件写入失败: {str(e)}")
                raise Exception(f"文件写入失败: {str(e)}")
        except Exception as e:
            self.status_update.emit(f"下载文件失败: {str(e)}")
            raise Exception(f"下载文件失败: {str(e)}")
    
    def convert_subtitle_to_srt(self, subtitle_data):
        """将B站字幕JSON转换为SRT格式"""
        try:
            srt_content = ""
            index = 1
            
            # 检查字幕数据格式
            if isinstance(subtitle_data, dict):
                if 'body' in subtitle_data:
                    subtitles = subtitle_data['body']
                elif 'data' in subtitle_data and isinstance(subtitle_data['data'], dict):
                    subtitles = subtitle_data['data'].get('body', [])
                else:
                    self.status_update.emit(f"字幕数据结构：{json.dumps(subtitle_data, ensure_ascii=False)[:200]}")
                    raise Exception("无法识别的字幕数据格式")
            elif isinstance(subtitle_data, list):
                subtitles = subtitle_data
            else:
                self.status_update.emit(f"未知的字幕数据类型：{type(subtitle_data)}")
                raise Exception("未知的字幕格式")
            
            if not subtitles:
                raise Exception("字幕内容为空")
                
            for item in subtitles:
                if not isinstance(item, dict):
                    self.status_update.emit(f"无效的字幕条目：{item}")
                    continue
                    
                try:
                    start_time = float(item.get('from', 0))
                    end_time = float(item.get('to', 0))
                    content = item.get('content', '').strip()
                    
                    if not content:
                        continue
                    
                    # 转换时间格式 (秒 -> HH:MM:SS,mmm)
                    start_formatted = self.format_time(start_time)
                    end_formatted = self.format_time(end_time)
                    
                    # 添加SRT条目
                    srt_content += f"{index}\n{start_formatted} --> {end_formatted}\n{content}\n\n"
                    index += 1
                except Exception as e:
                    self.status_update.emit(f"处理字幕条目时出错：{str(e)}，条目内容：{item}")
                    continue
            
            if not srt_content:
                raise Exception("转换后的字幕内容为空")
                
            return srt_content
        except Exception as e:
            raise Exception(f"字幕转换失败：{str(e)}")
    
    def format_time(self, seconds):
        """将秒转换为SRT时间格式 HH:MM:SS,mmm"""
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        seconds = seconds % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"
    
    def merge_video_audio(self, video_file, audio_file, output_file):
        try:
            import subprocess
            import os
            import sys
            
            # 获取程序运行目录
            if getattr(sys, 'frozen', False):
                # 如果是打包后的exe，使用实际的程序运行目录
                base_path = os.path.dirname(sys.executable)
            else:
                # 如果是开发环境
                base_path = os.path.dirname(os.path.abspath(__file__))
            
            # 在程序目录中查找ffmpeg.exe
            ffmpeg_path = os.path.join(base_path, 'ffmpeg.exe')
            if not os.path.exists(ffmpeg_path):
                # 如果在程序目录没找到，尝试在临时目录查找（用于处理某些打包情况）
                if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                    temp_path = os.path.join(sys._MEIPASS, 'ffmpeg.exe')
                    if os.path.exists(temp_path):
                        ffmpeg_path = temp_path
                    else:
                        raise Exception("找不到ffmpeg.exe，请确保程序目录中包含ffmpeg.exe文件")
                else:
                    raise Exception("找不到ffmpeg.exe，请确保程序目录中包含ffmpeg.exe文件")
            
            command = [
                ffmpeg_path,
                '-i', video_file,
                '-i', audio_file,
                '-c', 'copy',
                output_file
            ]
            subprocess.run(command, check=True)
        except Exception as e:
            raise Exception(f"合并音视频失败：{str(e)}")

class SubtitleSelectDialog(QDialog):
    def __init__(self, subtitles, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要下载的字幕")
        self.resize(500, 400)
        self.setMinimumSize(400, 300)
        
        self.selected_subtitles = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 添加标题
        title_label = QLabel("请选择要下载的字幕")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 字幕列表放在卡片中
        subtitle_card = CardFrame(self)
        subtitle_layout = QVBoxLayout()
        subtitle_layout.setContentsMargins(0, 0, 0, 0)
        subtitle_card.layout.addLayout(subtitle_layout)
        
        # 添加全选/取消全选按钮
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.deselect_all_btn)
        select_layout.addStretch()
        subtitle_layout.addLayout(select_layout)
        
        # 添加字幕复选框
        self.subtitle_checkboxes = []
        for sub in subtitles:
            sub_lan = sub.get('lan', 'unknown')
            sub_lan_doc = sub.get('lan_doc', sub_lan)
            checkbox = QCheckBox(f"{sub_lan_doc} ({sub_lan})")
            checkbox.setChecked(True)  # 默认全选
            checkbox.setProperty("lan", sub_lan)  # 存储语言代码
            self.subtitle_checkboxes.append(checkbox)
            subtitle_layout.addWidget(checkbox)
        
        layout.addWidget(subtitle_card)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setObjectName("accentButton")
        self.confirm_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.confirm_btn)
        layout.addLayout(button_layout)
        
        # 设置WinUI 3风格
        self.setStyleSheet("""
            QWidget {
                background-color: #f9f9f9;
                font-family: 'Segoe UI';
            }
            QLabel {
                font-size: 14px;
                color: #202020;
            }
        """)
    
    def select_all(self):
        for checkbox in self.subtitle_checkboxes:
            checkbox.setChecked(True)
    
    def deselect_all(self):
        for checkbox in self.subtitle_checkboxes:
            checkbox.setChecked(False)
    
    def accept(self):
        self.selected_subtitles = []
        for checkbox in self.subtitle_checkboxes:
            if checkbox.isChecked():
                self.selected_subtitles.append(checkbox.property("lan"))
        super().accept()
    
    def reject(self):
        self.selected_subtitles = []
        super().reject()

class QRCodeDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("扫码登录")
        # 移除固定大小设置，改为初始大小
        self.resize(500, 600)
        # 设置最小大小，防止窗口过小
        self.setMinimumSize(400, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 添加标题
        title_label = QLabel("B站扫码登录")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 二维码标签放在卡片中
        qr_card = CardFrame(self)
        qr_layout = QVBoxLayout()
        qr_layout.setContentsMargins(0, 0, 0, 0)
        qr_card.layout.addLayout(qr_layout)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 设置二维码最小大小
        self.qr_label.setMinimumSize(300, 300)
        qr_layout.addWidget(self.qr_label)
        
        layout.addWidget(qr_card)
        
        # 状态提示
        self.status_label = QLabel("请使用哔哩哔哩APP扫码")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 添加说明文字
        tip_label = QLabel("提示：打开哔哩哔哩APP，点击右上角扫一扫，扫描上方二维码登录")
        tip_label.setWordWrap(True)
        tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip_label.setStyleSheet("color: #666666; font-size: 12px;")
        layout.addWidget(tip_label)
        
        # 设置WinUI 3风格
        self.setStyleSheet("""
            QWidget {
                background-color: #f9f9f9;
                font-family: 'Segoe UI';
            }
            QLabel {
                font-size: 14px;
                color: #202020;
            }
        """)

class CardFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet("""
            #card {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(10)

class AboutDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("关于")
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("BiliDown-GUI")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 版本号
        version_label = QLabel("版本 v1.1.5-beta")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666666;")
        layout.addWidget(version_label)
        
        # 作者信息
        author_label = QLabel("作者: WatererQuan")
        author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(author_label)
        
        # GitHub链接
        github_link = QLabel('<a href="https://github.com/WatererQuan/BiliDown-GUI">GitHub仓库</a>')
        github_link.setOpenExternalLinks(True)
        github_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(github_link)
        
        # 描述
        desc_label = QLabel("一个简单易用的哔哩哔哩视频下载工具，支持登录下载高清视频。")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #666666; margin: 20px 0;")
        layout.addWidget(desc_label)

class BilibiliDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 初始化会话
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session.headers.update(self.headers)
        self.is_logged_in = False
        
        self.cookies_file = 'bilibili_cookies.json'
        self.load_cookies()
        
        # 初始化UI
        self.setWindowTitle("BiliDown-GUI v1.1.5-beta")
        self.setMinimumSize(1000, 800)
        self.setup_ui()
        
        # 创建菜单栏
        self.create_menu()
        
        # 初始化版本检查器
        self.version_checker = VersionChecker()
        self.version_checker.version_available.connect(self.on_update_available)
        self.version_checker.check_error.connect(self.on_update_check_error)
    
    def load_cookies(self):
        try:
            if os.path.exists(self.cookies_file):
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    self.session.cookies.update(cookies)
                    response = self.session.get('https://api.bilibili.com/x/web-interface/nav')
                    if response.json().get('data', {}).get('isLogin', False):
                        self.is_logged_in = True
                        self.nav_data = response.json()
                        return True
        except Exception:
            pass
        return False
    
    def save_cookies(self):
        try:
            cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f)
        except Exception as e:
            print(f"保存cookies失败：{str(e)}")
    
    def setup_ui(self):
        # 设置WinUI 3风格
        self.setup_winui_style()
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 顶部用户信息区域
        user_card = CardFrame()
        user_layout = QHBoxLayout()
        user_layout.setContentsMargins(0, 0, 0, 0)
        user_card.layout.addLayout(user_layout)
        
        # 用户头像
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(40, 40)
        self.set_default_avatar()
        user_layout.addWidget(self.avatar_label)
        
        # 用户信息
        user_info_layout = QVBoxLayout()
        user_info_layout.setSpacing(2)
        self.login_status_label = QLabel("未登录")
        self.user_level_label = QLabel("")
        user_info_layout.addWidget(self.login_status_label)
        user_info_layout.addWidget(self.user_level_label)
        user_layout.addLayout(user_info_layout)
        
        # 登录按钮
        self.login_button = QPushButton("登录")
        self.login_button.setObjectName("accentButton")
        self.login_button.clicked.connect(self.start_login)
        user_layout.addWidget(self.login_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        main_layout.addWidget(user_card)
        
        # 视频信息卡片
        video_card = CardFrame()
        video_card.layout.addWidget(QLabel("视频信息"))
        
        # BV号输入
        bv_layout = QHBoxLayout()
        bv_layout.addWidget(QLabel("视频链接或BV号："))
        self.bv_entry = QLineEdit()
        self.bv_entry.setPlaceholderText("输入BV号或视频链接")
        self.bv_entry.textChanged.connect(self.on_url_change)
        bv_layout.addWidget(self.bv_entry)
        video_card.layout.addLayout(bv_layout)
        
        # 分P选择
        page_layout = QHBoxLayout()
        page_layout.addWidget(QLabel("选择分P："))
        self.page_combo = QComboBox()
        self.page_combo.setMinimumWidth(400)
        page_layout.addWidget(self.page_combo)
        video_card.layout.addLayout(page_layout)
        
        main_layout.addWidget(video_card)
        
        # 下载设置卡片
        settings_card = CardFrame()
        settings_card.layout.addWidget(QLabel("下载设置"))
        
        # 下载路径
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("下载路径："))
        self.path_entry = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_entry)
        path_button = QPushButton("选择")
        path_button.clicked.connect(self.choose_download_path)
        path_layout.addWidget(path_button)
        open_folder_button = QPushButton("打开文件夹")
        open_folder_button.clicked.connect(self.open_download_folder)
        path_layout.addWidget(open_folder_button)
        settings_card.layout.addLayout(path_layout)
        
        # 下载选项
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("下载内容："))
        self.video_check = QCheckBox("视频")
        self.video_check.setChecked(True)
        self.audio_check = QCheckBox("音频")
        self.audio_check.setChecked(True)
        self.subtitle_check = QCheckBox("字幕(待开发)")
        self.subtitle_check.setEnabled(False)
        self.cover_check = QCheckBox("封面")
        options_layout.addWidget(self.video_check)
        options_layout.addWidget(self.audio_check)
        options_layout.addWidget(self.subtitle_check)
        options_layout.addWidget(self.cover_check)
        options_layout.addStretch()
        settings_card.layout.addLayout(options_layout)
        
        # 画质选择
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("画质："))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "127 (8K) - 大会员专享",
            "126 (杜比视界) - 大会员专享",
            "125 (HDR) - 大会员专享",
            "120 (4K) - 大会员专享",
            "116 (1080P60) - 大会员专享",
            "112 (1080P+) - 大会员专享",
            "80 (1080P) - 登录下载",
            "74 (720P60) - 登录下载",
            "64 (720P) - 登录下载",
            "32 (480P) - 登录下载",
            "16 (360P) - 免费下载"
        ])
        self.quality_combo.setCurrentIndex(6)  # 默认1080P
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        settings_card.layout.addLayout(quality_layout)
        
        # 接口选择
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("接口选择："))
        self.api_combo = QComboBox()
        self.api_combo.addItems(["官方", "解析接口1", "RapidAPI", "BiliAPI"])
        api_layout.addWidget(self.api_combo)
        api_layout.addStretch()
        settings_card.layout.addLayout(api_layout)
        
        main_layout.addWidget(settings_card)
        
        # 下载控制卡片
        control_card = CardFrame()
        control_card.layout.addWidget(QLabel("下载控制"))
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)  # 设置为可见，以显示文件大小
        self.progress_bar.setFormat("%p%")  # 默认格式
        control_card.layout.addWidget(self.progress_bar)
        
        # 状态信息
        status_layout = QHBoxLayout()
        self.speed_label = QLabel("")
        self.status_label = QLabel("")
        status_layout.addWidget(self.speed_label)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        control_card.layout.addLayout(status_layout)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("开始下载")
        self.download_button.setObjectName("accentButton")
        self.download_button.clicked.connect(self.start_download)
        
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.pause_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        control_card.layout.addLayout(button_layout)
        
        main_layout.addWidget(control_card)
        
        # 初始化下载线程
        self.download_thread = None
        self.login_thread = None
        self.downloading = False
        self.paused = False
        
        # 更新用户信息
        if self.is_logged_in:
            self.update_user_info(self.nav_data)
        
    def create_menu(self):
        menubar = self.menuBar()
        help_menu = menubar.addMenu('帮助')
        
        about_action = help_menu.addAction('关于')
        about_action.triggered.connect(self.show_about)
    
    def show_about(self):
        about_dialog = AboutDialog(self)
        about_dialog.show()
    
    def create_menu(self):
        menubar = self.menuBar()
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        
        # 检查更新选项
        check_update_action = help_menu.addAction('检查更新')
        check_update_action.triggered.connect(self.check_update)
        
        # 关于选项
        about_action = help_menu.addAction('关于')
        about_action.triggered.connect(self.show_about)
    
    def check_update(self):
        """检查更新"""
        self.version_checker.start()
    
    def on_update_available(self, new_version, download_url):
        """有新版本可用时的处理函数"""
        show_update_dialog(self, new_version, download_url)
    
    def on_update_check_error(self, error_message):
        """检查更新出错时的处理函数"""
        QMessageBox.warning(self, '检查更新失败', error_message)
    
    def setup_winui_style(self):
        # 设置WinUI 3风格
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f9f9f9;
            }
            QLabel {
                font-family: 'Segoe UI';
                font-size: 14px;
                color: #202020;
            }
            QPushButton {
                font-family: 'Segoe UI';
                font-size: 14px;
                padding: 8px 16px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: #f5f5f5;
                color: #202020;
            }
            QPushButton:hover {
                background-color: #e5e5e5;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            #accentButton {
                background-color: #0078d7;
                color: white;
                border: none;
            }
            #accentButton:hover {
                background-color: #1a86d9;
            }
            #accentButton:pressed {
                background-color: #006cc1;
            }
            QLineEdit, QComboBox {
                font-family: 'Segoe UI';
                font-size: 14px;
                padding: 8px;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                background-color: white;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #f0f0f0;
                height: 6px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0078d7;
                border-radius: 3px;
            }
            QCheckBox {
                font-family: 'Segoe UI';
                font-size: 14px;
                color: #202020;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d7;
                border: 1px solid #0078d7;
            }
        """)
    
    def set_default_avatar(self):
        pixmap = QPixmap(40, 40)
        pixmap.fill(QColor('#f0f0f0'))
        self.avatar_label.setPixmap(pixmap)
    
    def update_user_info(self, nav_data):
        try:
            uname = nav_data['data'].get('uname', '')
            level = nav_data['data'].get('level_info', {}).get('current_level', 0)
            self.login_status_label.setText(f"昵称：{uname}")
            self.user_level_label.setText(f"等级：LV{level}")
            self.login_button.setText("退出登录")
            
            face_url = nav_data['data'].get('face', '')
            if face_url:
                response = requests.get(face_url)
                avatar_image = Image.open(BytesIO(response.content))
                avatar_image = avatar_image.resize((40, 40))
                
                # 转换为QPixmap
                bio = BytesIO()
                avatar_image.save(bio, format='PNG')
                pixmap = QPixmap()
                pixmap.loadFromData(bio.getvalue())
                self.avatar_label.setPixmap(pixmap)
        except Exception as e:
            print(f"更新用户信息失败：{str(e)}")
    
    def on_url_change(self):
        text = self.bv_entry.text().strip()
        if 'bilibili.com' in text:
            bv_match = re.search(r'BV\w+', text)
            if bv_match:
                bv_number = bv_match.group()
                self.bv_entry.setText(bv_number)
                self.update_page_list(bv_number)
    
    def update_page_list(self, bvid):
        try:
            self.status_label.setText("获取视频信息...")
            video_info = self.get_video_info(bvid)
            if 'pages' in video_info:
                pages = video_info['pages']
                self.page_combo.clear()
                for p in pages:
                    self.page_combo.addItem(f"{p['page']}. {p['part']}", p['cid'])
                self.status_label.setText("")
        except Exception as e:
            self.status_label.setText(f"获取分P信息失败：{str(e)}")
    
    def get_video_info(self, bvid):
        url = f"https://api.bilibili.com/x/web-interface/view"
        params = {'bvid': bvid}
        response = self.session.get(url, params=params)
        data = response.json()
        if data.get('code') != 0:
            raise Exception(f"获取视频信息失败：{data.get('message', '未知错误')}")
        return data['data']
    
    def start_login(self):
        if self.is_logged_in:
            # 退出登录
            self.session.cookies.clear()
            if os.path.exists(self.cookies_file):
                os.remove(self.cookies_file)
            self.is_logged_in = False
            self.login_button.setText("登录")
            self.login_status_label.setText("未登录")
            self.user_level_label.setText("")
            self.set_default_avatar()
            QMessageBox.information(self, "提示", "已退出登录！")
        else:
            # 开始登录
            self.login_button.setEnabled(False)
            self.status_label.setText("正在获取登录二维码...")
            
            # 创建登录线程
            self.login_thread = LoginThread(self.session)
            self.login_thread.login_success.connect(self.on_login_success)
            self.login_thread.login_failed.connect(self.on_login_failed)
            self.login_thread.qrcode_ready.connect(self.show_qrcode)
            self.login_thread.status_update.connect(self.status_label.setText)
            self.login_thread.start()
    
    def on_login_success(self, nav_data):
        self.is_logged_in = True
        self.save_cookies()
        self.update_user_info(nav_data)
        self.login_button.setEnabled(True)
        self.status_label.setText("登录成功！")
        if hasattr(self, 'qr_dialog') and self.qr_dialog:
            self.qr_dialog.close()
        QMessageBox.information(self, "提示", "登录成功！")
    
    def on_login_failed(self, error_msg):
        self.login_button.setEnabled(True)
        self.status_label.setText(f"登录失败：{error_msg}")
        if hasattr(self, 'qr_dialog') and self.qr_dialog:
            self.qr_dialog.close()
        QMessageBox.critical(self, "错误", f"登录失败：{error_msg}")
    
    def show_qrcode(self, qr_pixmap):
        # 创建二维码对话框
        self.qr_dialog = QRCodeDialog(self)
        self.qr_dialog.qr_label.setPixmap(qr_pixmap)
        self.qr_dialog.show()
    
    def choose_download_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择下载目录", self.path_entry.text())
        if path:
            self.path_entry.setText(path)
    
    def open_download_folder(self):
        path = self.path_entry.text()
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "提示", "下载文件夹不存在！")
    
    def start_download(self):
        bvid = self.bv_entry.text().strip()
        if not bvid:
            QMessageBox.warning(self, "提示", "请输入BV号！")
            return
        
        # 获取当前选中的分P
        current_index = self.page_combo.currentIndex()
        if current_index == -1:
            QMessageBox.warning(self, "提示", "请先选择分P！")
            return
        
        cid = self.page_combo.itemData(current_index)
        
        # 获取画质
        quality_text = self.quality_combo.currentText()
        quality = int(quality_text.split()[0])
        
        # 获取下载选项
        options = {
            'video': self.video_check.isChecked(),
            'audio': self.audio_check.isChecked(),
            'subtitle': self.subtitle_check.isChecked(),
            'cover': self.cover_check.isChecked()
        }
        
        # 如果选择了下载字幕，先获取字幕列表并让用户选择
        if options['subtitle']:
            try:
                self.status_label.setText("获取字幕信息...")
                subtitle_url = f"https://api.bilibili.com/x/player/v2?cid={cid}&bvid={bvid}"
                subtitle_response = self.session.get(subtitle_url)
                subtitle_data = subtitle_response.json()
                
                # 检查是否有字幕
                subtitles = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
                
                if not subtitles:
                    self.status_label.setText("该视频没有字幕")
                    options['subtitle'] = False
                else:
                    # 显示字幕选择对话框
                    subtitle_dialog = SubtitleSelectDialog(subtitles, self)
                    if subtitle_dialog.exec() == QDialog.DialogCode.Accepted:
                        selected_subtitles = subtitle_dialog.selected_subtitles
                        # 如果用户没有选择任何字幕，则不下载字幕
                        if not selected_subtitles:
                            options['subtitle'] = False
                        else:
                            options['selected_subtitles'] = selected_subtitles
                    else:
                        # 用户取消了选择，不下载字幕
                        options['subtitle'] = False
            except Exception as e:
                self.status_label.setText(f"获取字幕信息失败: {str(e)}")
                options['subtitle'] = False
        
        # 获取下载路径
        download_path = self.path_entry.text()
        
        # 获取API类型
        api_type = self.api_combo.currentText()
        
        # 禁用下载按钮，启用暂停和取消按钮
        self.download_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        
        # 创建下载线程
        self.download_thread = DownloadThread(
            self.session, bvid, cid, quality, download_path, options, api_type
        )
        
        # 连接信号
        self.download_thread.progress_update.connect(self.update_progress)
        self.download_thread.speed_update.connect(self.update_speed)
        self.download_thread.status_update.connect(self.status_label.setText)
        self.download_thread.download_complete.connect(self.on_download_complete)
        self.download_thread.download_error.connect(self.on_download_error)
        
        # 重置进度条显示
        self.progress_bar.setTextVisible(True)
        
        # 开始下载
        self.download_thread.start()
    
    def update_progress(self, current, total):
        if total > 0:
            percentage = int(current * 100 / total)
            self.progress_bar.setValue(percentage)
            # 显示下载大小信息
            downloaded_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self.progress_bar.setFormat(f"{downloaded_mb:.1f}MB / {total_mb:.1f}MB (%p%)")
            self.progress_bar.setTextVisible(True)  # 确保文本可见
            self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def update_speed(self, speed_bytes):
        speed_mb = speed_bytes / 1024 / 1024
        self.speed_label.setText(f"下载速度: {speed_mb:.2f} MB/s")
    
    def on_download_complete(self):
        self.download_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(100)
        self.speed_label.setText("")
        QMessageBox.information(self, "提示", "下载完成！")
    
    def on_download_error(self, error_msg):
        self.download_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.speed_label.setText("")
        self.status_label.setText(f"下载失败：{error_msg}")
        QMessageBox.critical(self, "错误", f"下载失败：{error_msg}")
    
    def toggle_pause(self):
        if hasattr(self, 'download_thread') and self.download_thread:
            self.download_thread.paused = not self.download_thread.paused
            self.pause_button.setText("继续" if self.download_thread.paused else "暂停")
    
    def cancel_download(self):
        if hasattr(self, 'download_thread') and self.download_thread:
            self.download_thread.cancel = True
            self.status_label.setText("正在取消下载...")
            self.download_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            
            # 确保下载线程正确终止
            self.download_thread.quit()
            self.download_thread.wait(1000)  # 等待最多1秒
            
            # 如果线程仍在运行，强制终止
            if self.download_thread.isRunning():
                self.download_thread.terminate()
                
            # 重置UI状态
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.speed_label.setText("")
            self.status_label.setText("下载已取消")
            self.download_thread = None

# 主函数
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BilibiliDownloaderGUI()
    window.show()
    sys.exit(app.exec())