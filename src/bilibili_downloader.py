import requests
import json
import qrcode
import time
from PIL import Image
import os
from concurrent.futures import ThreadPoolExecutor

class BilibiliDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session.headers.update(self.headers)
        self.is_logged_in = False

    def login(self):
        """使用二维码登录B站"""
        # 获取二维码登录URL
        qr_url = "https://passport.bilibili.com/qrcode/getLoginUrl"
        response = self.session.get(qr_url)
        data = response.json()['data']
        
        # 生成二维码
        qr = qrcode.QRCode()
        qr.add_data(data['url'])
        qr.make()
        img = qr.make_image()
        img.save('qrcode.png')
        
        # 打开二维码图片
        Image.open('qrcode.png').show()
        
        # 检查登录状态
        while not self.is_logged_in:
            check_url = f"https://passport.bilibili.com/qrcode/getLoginInfo"
            response = self.session.post(check_url, data={
                'oauthKey': data['oauthKey']
            })
            
            if response.json()['status']:
                self.is_logged_in = True
                print("登录成功！")
                break
            
            time.sleep(2)
        
        os.remove('qrcode.png')

    def get_video_info(self, bvid):
        """获取视频信息"""
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        response = self.session.get(url)
        return response.json()['data']

    def get_download_url(self, bvid, cid, quality):
        """获取视频下载地址"""
        url = f"https://api.bilibili.com/x/player/playurl"
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': quality,
            'fnval': 16
        }
        response = self.session.get(url, params=params)
        return response.json()['data']

    def download_video(self, url, filename):
        """下载视频"""
        response = self.session.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def start_download(self, bvid):
        """开始下载流程"""
        if not self.is_logged_in:
            print("请先登录！")
            self.login()

        # 获取视频信息
        video_info = self.get_video_info(bvid)
        print(f"视频标题：{video_info['title']}")

        # 显示可用画质
        qualities = {
            80: '1080P',
            64: '720P',
            32: '480P',
            16: '360P'
        }
        print("\n可用画质：")
        for qn, name in qualities.items():
            print(f"{qn}: {name}")
        
        quality = int(input("请选择画质(输入数字)："))

        # 获取下载地址
        download_info = self.get_download_url(bvid, video_info['cid'], quality)
        
        # 下载视频
        video_url = download_info['durl'][0]['url']
        filename = f"{video_info['title']}.mp4"
        print(f"\n开始下载：{filename}")
        self.download_video(video_url, filename)
        print("下载完成！")

if __name__ == "__main__":
    downloader = BilibiliDownloader()
    bvid = input("请输入BV号：")
    downloader.start_download(bvid)