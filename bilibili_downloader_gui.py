import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import json
import qrcode
import time
from PIL import Image, ImageTk
import os
import threading
from io import BytesIO
import re

class BilibiliDownloaderGUI:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("B站视频下载器")
        self.window.geometry("800x600")
        
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session.headers.update(self.headers)
        self.is_logged_in = False
        self.cancel_login = False
        
        self.cookies_file = 'bilibili_cookies.json'
        self.load_cookies()
        
        self.setup_gui()

    def load_cookies(self):
        try:
            if os.path.exists(self.cookies_file):
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    self.session.cookies.update(cookies)
                    response = self.session.get('https://api.bilibili.com/x/web-interface/nav')
                    if response.json().get('data', {}).get('isLogin', False):
                        self.is_logged_in = True
                        return True
        except Exception:
            pass
        return False

    def save_cookies(self):  # 添加这个方法
        """保存当前cookies到文件"""
        try:
            cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f)
        except Exception as e:
            print(f"保存cookies失败：{str(e)}")

    def setup_gui(self):
        # 登录框架
        self.login_frame = ttk.LabelFrame(self.window, text="账号信息", padding="10")
        self.login_frame.pack(fill="x", padx=10, pady=5)
        
        self.user_info_frame = ttk.Frame(self.login_frame)
        self.user_info_frame.pack(side="left", fill="x", expand=True)
        
        self.avatar_label = ttk.Label(self.user_info_frame)
        self.avatar_label.pack(side="left", padx=5)
        self.set_default_avatar()
        
        self.user_detail_frame = ttk.Frame(self.user_info_frame)
        self.user_detail_frame.pack(side="left", padx=10)
        
        self.login_status = ttk.Label(self.user_detail_frame, text="未登录")
        self.login_status.pack(anchor="w")
        self.user_level = ttk.Label(self.user_detail_frame, text="")
        self.user_level.pack(anchor="w")
        
        self.login_button = ttk.Button(self.login_frame, text="登录", command=self.start_login)
        self.login_button.pack(side="right")
        
        # 下载框架
        self.download_frame = ttk.LabelFrame(self.window, text="视频下载", padding="10")
        self.download_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 下载设置
        self.settings_frame = ttk.LabelFrame(self.download_frame, text="下载设置", padding="10")
        self.settings_frame.pack(fill="x", pady=5)
        
        path_frame = ttk.Frame(self.settings_frame)
        path_frame.pack(fill="x", pady=5)
        ttk.Label(path_frame, text="下载路径：").pack(side="left")
        self.path_var = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=40)
        self.path_entry.pack(side="left", padx=5)
        ttk.Button(path_frame, text="选择", command=self.choose_download_path).pack(side="left")
        ttk.Button(path_frame, text="打开文件夹", command=self.open_download_folder).pack(side="left", padx=5)
        
        options_frame = ttk.Frame(self.settings_frame)
        options_frame.pack(fill="x", pady=5)
        
        self.video_var = tk.BooleanVar(value=True)
        self.audio_var = tk.BooleanVar(value=True)
        self.subtitle_var = tk.BooleanVar(value=False)
        self.cover_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(options_frame, text="视频", variable=self.video_var).pack(side="left", padx=10)
        ttk.Checkbutton(options_frame, text="音频", variable=self.audio_var).pack(side="left", padx=10)
        ttk.Checkbutton(options_frame, text="字幕", variable=self.subtitle_var).pack(side="left", padx=10)
        ttk.Checkbutton(options_frame, text="封面", variable=self.cover_var).pack(side="left", padx=10)

        # 分P选择
        self.page_frame = ttk.Frame(self.download_frame)
        self.page_frame.pack(pady=5)
        ttk.Label(self.page_frame, text="选择分P：").pack(side="left")
        self.page_var = tk.StringVar(value="1")
        self.page_combo = ttk.Combobox(self.page_frame, textvariable=self.page_var, width=40, state="readonly")
        self.page_combo.pack(side="left")
        
        # BV号输入
        ttk.Label(self.download_frame, text="视频链接或BV号：").pack()
        self.bv_entry = ttk.Entry(self.download_frame, width=50)
        self.bv_entry.pack(pady=5)
        self.bv_entry.bind('<KeyRelease>', self.on_url_change)
        
        # 画质选择
        self.quality_frame = ttk.Frame(self.download_frame)
        self.quality_frame.pack(pady=5)
        ttk.Label(self.quality_frame, text="画质：").pack(side="left")
        self.quality_var = tk.StringVar(value="80")
        self.quality_combo = ttk.Combobox(self.quality_frame, 
                                        textvariable=self.quality_var,
                                        values=[
                                            "120 (4K) - 大会员专享",
                                            "116 (1080P60) - 大会员专享",
                                            "80 (1080P) - 登录下载",
                                            "64 (720P) - 登录下载",
                                            "32 (480P) - 登录下载",
                                            "16 (360P) - 免费下载"
                                        ],
                                        state="readonly",
                                        width=20)
        self.quality_combo.pack(side="left")
        
        # 接口选择
        self.api_frame = ttk.Frame(self.download_frame)
        self.api_frame.pack(pady=5)
        ttk.Label(self.api_frame, text="接口选择：").pack(side="left")
        self.api_var = tk.StringVar(value="官方")
        self.api_combo = ttk.Combobox(self.api_frame, 
                                    textvariable=self.api_var,
                                    values=["官方", "解析接口1", "RapidAPI", "BiliAPI"],
                                    state="readonly",
                                    width=20)
        self.api_combo.pack(side="left")
        
        # 下载控制按钮框架
        self.control_frame = ttk.Frame(self.download_frame)
        self.control_frame.pack(pady=5)
        
        self.download_button = ttk.Button(self.control_frame, text="开始下载", command=self.start_download)
        self.download_button.pack(side="left", padx=5)
        
        self.pause_button = ttk.Button(self.control_frame, text="暂停", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=5)
        
        self.cancel_button = ttk.Button(self.control_frame, text="取消", command=self.cancel_download, state="disabled")
        self.cancel_button.pack(side="left", padx=5)
        
        self.progress = ttk.Progressbar(self.download_frame, length=400, mode='determinate')
        self.progress.pack(pady=5)
        
        self.speed_label = ttk.Label(self.download_frame, text="")
        self.speed_label.pack()
        
        self.status_label = ttk.Label(self.download_frame, text="")
        self.status_label.pack()
        
        # 下载控制变量
        self.downloading = False
        self.paused = False

        if self.is_logged_in:
            self.login_status.config(text="已登录")
            self.login_button.config(text="退出登录")

    def set_default_avatar(self):
        default_avatar = Image.new('RGB', (40, 40), color='#f0f0f0')
        photo = ImageTk.PhotoImage(default_avatar)
        self.avatar_label.configure(image=photo)
        self.avatar_label.image = photo

    def choose_download_path(self):
        path = filedialog.askdirectory(initialdir=self.path_var.get())
        if path:
            self.path_var.set(path)
            
    def open_download_folder(self):
        path = self.path_var.get()
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("提示", "下载文件夹不存在！")

    def update_user_info(self, nav_data):
        try:
            uname = nav_data['data'].get('uname', '')
            level = nav_data['data'].get('level_info', {}).get('current_level', 0)
            self.login_status.config(text=f"昵称：{uname}")
            self.user_level.config(text=f"等级：LV{level}")
            
            face_url = nav_data['data'].get('face', '')
            if face_url:
                response = requests.get(face_url)
                avatar_image = Image.open(BytesIO(response.content))
                avatar_image = avatar_image.resize((40, 40))
                photo = ImageTk.PhotoImage(avatar_image)
                self.avatar_label.configure(image=photo)
                self.avatar_label.image = photo
        except Exception as e:
            print(f"更新用户信息失败：{str(e)}")

    def on_url_change(self, event):
        text = self.bv_entry.get().strip()
        if 'bilibili.com' in text:
            bv_match = re.search(r'BV\w+', text)
            if bv_match:
                bv_number = bv_match.group()
                self.bv_entry.delete(0, tk.END)
                self.bv_entry.insert(0, bv_number)
                self.update_page_list(bv_number)

    def update_page_list(self, bvid):
        try:
            video_info = self.get_video_info(bvid)
            if 'pages' in video_info:
                pages = video_info['pages']
                page_list = [f"{p['page']}. {p['part']}" for p in pages]
                self.page_combo['values'] = page_list
                if page_list:
                    self.page_combo.set(page_list[0])
        except Exception as e:
            print(f"获取分P信息失败：{str(e)}")

    def start_login(self):
        if self.is_logged_in:
            # 退出登录
            self.session.cookies.clear()
            if os.path.exists(self.cookies_file):
                os.remove(self.cookies_file)
            self.is_logged_in = False
            self.login_button.config(text="登录")
            self.login_status.config(text="未登录")
            self.user_level.config(text="")
            self.set_default_avatar()
            messagebox.showinfo("提示", "已退出登录！")
        else:
            # 开始登录
            self.login_button.config(state="disabled")
            self.update_status("正在获取登录二维码...")
            threading.Thread(target=self.login_process, daemon=True).start()

    def login_process(self):
        try:
            # 使用新的二维码生成接口
            qr_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            response = self.session.get(qr_url)
            if response.status_code != 200:
                raise Exception("获取二维码失败：服务器无响应")
            
            data = response.json()
            if data.get('code') != 0:
                raise Exception(f"获取二维码失败：{data.get('message', '未知错误')}")

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
            
            # 创建二维码窗口
            qr_window = tk.Toplevel(self.window)
            qr_window.title("扫码登录")
            qr_window.geometry("300x400")
            
            img = Image.open(bio)
            photo = ImageTk.PhotoImage(img)
            label = ttk.Label(qr_window, image=photo)
            label.image = photo  # 保持图片引用
            label.pack(pady=10)
            
            status_label = ttk.Label(qr_window, text="请使用哔哩哔哩APP扫码")
            status_label.pack()
            
            # 开始检查登录状态
            self.check_login_status(qrcode_key, qr_window, status_label)
            
        except Exception as e:
            messagebox.showerror("错误", f"登录失败：{str(e)}")
            self.login_button.config(state="normal")

    def check_login_status(self, qrcode_key, qr_window, status_label):
        if self.cancel_login:
            qr_window.destroy()
            return
            
        try:
            check_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
            params = {'qrcode_key': qrcode_key}
            response = self.session.get(check_url, params=params)
            
            # 检查响应有效性
            if response.status_code != 200:
                raise Exception("服务器响应异常")
            if not response.content:
                raise Exception("服务器返回空响应")
                
            data = response.json()
            
            # 处理不同状态码
            if data['code'] == 0:
                if data['data']['code'] == 0:  # 登录成功
                    self.save_cookies()
                    self.is_logged_in = True
                    self.update_user_info()
                    qr_window.destroy()
                    messagebox.showinfo("提示", "登录成功！")
                    return
                elif data['data']['code'] == 86038:  # 二维码过期
                    status_label.config(text="二维码已过期，请重新扫码")
                    return
                elif data['data']['code'] == 86090:  # 已扫码未确认
                    status_label.config(text="已扫码，请在APP确认登录")
            else:
                raise Exception(f"登录失败：{data.get('message', '未知错误')}")
                
            # 每1秒轮询一次
            self.window.after(1000, lambda: self.check_login_status(qrcode_key, qr_window, status_label))
            
        except json.JSONDecodeError:
            error_msg = "服务器返回了无效的响应"
            status_label.config(text=error_msg)
            qr_window.after(5000, qr_window.destroy)
        except Exception as e:
            status_label.config(text=str(e))
            qr_window.after(5000, qr_window.destroy)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.config(text="继续" if self.paused else "暂停")
    
    def cancel_download(self):
        self.downloading = False
        self.update_status("下载已取消")
    
    def start_download(self):
        bvid = self.bv_entry.get().strip()
        if not bvid:
            messagebox.showwarning("提示", "请输入BV号！")
            return
        
        quality = int(self.quality_var.get().split()[0])
        self.download_button.config(state="disabled")
        self.pause_button.config(state="normal")
        self.cancel_button.config(state="normal")
        self.downloading = True
        self.paused = False
        threading.Thread(target=self.download_process, args=(bvid,), daemon=True).start()

    def download_process(self, bvid):
        try:
            self.update_status("获取视频信息...")
            video_info = self.get_video_info(bvid)
            
            page_index = int(self.page_var.get().split('.')[0]) - 1
            current_page = video_info['pages'][page_index]
            cid = current_page['cid']
            
            download_path = self.path_var.get()
            os.makedirs(download_path, exist_ok=True)
            
            base_name = f"{video_info['title']}"
            if len(video_info['pages']) > 1:
                base_name += f"_P{current_page['page']}_{current_page['part']}"
            
            if self.cover_var.get():
                self.update_status("下载封面...")
                cover_url = video_info.get('pic', '')
                if cover_url:
                    cover_path = os.path.join(download_path, f"{base_name}.jpg")
                    self.download_file(cover_url, cover_path)
            
            if self.subtitle_var.get():
                self.update_status("下载字幕...")
                subtitle_url = f"https://api.bilibili.com/x/player/v2?cid={cid}&bvid={bvid}"
                subtitle_response = self.session.get(subtitle_url)
                subtitle_data = subtitle_response.json()
                subtitles = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
                for sub in subtitles:
                    sub_url = "https:" + sub.get('subtitle_url', '')
                    if sub_url:
                        sub_path = os.path.join(download_path, f"{base_name}_{sub['lan']}.srt")
                        self.download_file(sub_url, sub_path)
            
            quality = int(self.quality_var.get().split()[0])
            self.update_status("获取下载地址...")
            download_info = self.get_download_url(bvid, cid, quality)
            
            if 'dash' in download_info:
                if self.video_var.get() or self.audio_var.get():
                    video_path = os.path.join(download_path, f"{base_name}.mp4")
                    
                    if self.video_var.get() and self.audio_var.get():
                        temp_video = video_path + '.video.mp4'
                        temp_audio = video_path + '.audio.m4a'
                        
                        self.update_status("下载视频流...")
                        self.download_video(download_info['dash']['video'][0]['baseUrl'], temp_video)
                        
                        self.update_status("下载音频流...")
                        self.download_video(download_info['dash']['audio'][0]['baseUrl'], temp_audio)
                        
                        self.update_status("合并音视频...")
                        self.merge_video_audio(temp_video, temp_audio, video_path)
                        
                        os.remove(temp_video)
                        os.remove(temp_audio)
                    elif self.video_var.get():
                        self.update_status("下载视频流...")
                        self.download_video(download_info['dash']['video'][0]['baseUrl'], video_path)
                    elif self.audio_var.get():
                        audio_path = os.path.join(download_path, f"{base_name}.m4a")
                        self.update_status("下载音频流...")
                        self.download_video(download_info['dash']['audio'][0]['baseUrl'], audio_path)
            
            self.update_status("下载完成！")
            messagebox.showinfo("提示", "下载完成！")
        except Exception as e:
            messagebox.showerror("错误", f"下载失败：{str(e)}")
        finally:
            self.download_button.config(state="normal")
            self.progress['value'] = 0

    def get_download_url(self, bvid, cid, quality):
        api_type = self.api_var.get()
        if api_type == "官方":
            return self._get_official_download_url(bvid, cid, quality)
        else:
            return self._get_third_party_download_url(bvid)

    def _get_official_download_url(self, bvid, cid, quality):
        url = f"https://api.bilibili.com/x/player/playurl"
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': quality,
            'fnval': 4048,
            'fnver': 0,
            'fourk': 1,
            'platform': 'pc',
            'high_quality': 1,
            'otype': 'json'
        }
        headers = {
            'Referer': f'https://www.bilibili.com/video/{bvid}',
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

    def _get_third_party_download_url(self, bvid):
        api_type = self.api_var.get()
        quality = int(self.quality_var.get().split()[0])
        
        try:
            if api_type == "解析接口1":
                api_url = f"https://api.injahow.cn/bparse/?bv={bvid}&p=1&format=mp4&quality={quality}"
            elif api_type == "RapidAPI":
                api_url = f"https://bilibili-video-api.p.rapidapi.com/video/{bvid}"
                headers = {
                    'X-RapidAPI-Key': '在此填入你的RapidAPI密钥',
                    'X-RapidAPI-Host': 'bilibili-video-api.p.rapidapi.com'
                }
            elif api_type == "BiliAPI":
                api_url = f"https://bili-api.vercel.app/video/{bvid}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'https://www.bilibili.com/video/{bvid}'
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

    def download_video(self, url, filename):
        headers = {
            'Referer': 'https://www.bilibili.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Range': 'bytes=0-'
        }
        
        response = self.session.get(url, stream=True, headers=headers)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024 * 1024  # 1MB块大小
        
        self.progress['maximum'] = total_size
        self.downloading = True
        self.download_start_time = time.time()
        downloaded_size = 0
        last_update_time = time.time()
        last_downloaded_size = 0
        
        try:
            with open(filename, 'wb') as f:
                for data in response.iter_content(block_size):
                    if not self.downloading:  # 检查是否取消下载
                        raise Exception("下载已取消")
                    
                    while self.paused:  # 暂停下载
                        time.sleep(0.1)
                        if not self.downloading:  # 在暂停时检查是否取消
                            raise Exception("下载已取消")
                    
                    if data:  # 确保数据不为空
                        downloaded_size += len(data)
                        f.write(data)
                        self.progress['value'] = downloaded_size
                        
                        # 计算下载速度
                        current_time = time.time()
                        if current_time - last_update_time >= 1.0:  # 每秒更新一次速度
                            speed = (downloaded_size - last_downloaded_size) / (current_time - last_update_time)
                            speed_text = f"{speed/1024/1024:.2f} MB/s"
                            progress_text = f"{downloaded_size/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB"
                            self.speed_label.config(text=f"下载速度：{speed_text}")
                            self.status_label.config(text=f"下载进度：{progress_text}")
                            
                            last_update_time = current_time
                            last_downloaded_size = downloaded_size
                        
                        self.window.update()
        except Exception as e:
            if str(e) != "下载已取消":
                raise e
        finally:
            self.downloading = False
            self.paused = False
            self.download_button.config(state="normal")
            self.pause_button.config(state="disabled")
            self.cancel_button.config(state="disabled")

    def download_file(self, url, filename):
        try:
            response = requests.get(url)
            with open(filename, 'wb') as f:
                f.write(response.content)
        except Exception as e:
            print(f"下载文件失败：{str(e)}")

    def merge_video_audio(self, video_file, audio_file, output_file):
        try:
            import subprocess
            command = [
                'ffmpeg',
                '-i', video_file,
                '-i', audio_file,
                '-c', 'copy',
                output_file
            ]
            subprocess.run(command, check=True)
        except Exception as e:
            raise Exception(f"合并音视频失败：{str(e)}")

    def get_video_info(self, bvid):
        url = f"https://api.bilibili.com/x/web-interface/view"
        params = {'bvid': bvid}
        response = self.session.get(url, params=params)
        data = response.json()
        if data.get('code') != 0:
            raise Exception(f"获取视频信息失败：{data.get('message', '未知错误')}")
        return data['data']

    def update_status(self, text):
        self.status_label.config(text=text)
        self.window.update()

if __name__ == "__main__":
    app = BilibiliDownloaderGUI()
    app.window.mainloop()