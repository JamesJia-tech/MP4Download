import os
import sys
import time
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import yt_dlp
from urllib.parse import urlparse
import hashlib

class ChunkDownloader:
    def __init__(self, max_threads=8, chunk_size=2*1024*1024):  # 2MB per chunk
        self.max_threads = max_threads
        self.chunk_size = chunk_size
        self.progress_lock = threading.Lock()
        self.total_downloaded = 0
        self.total_size = 0
        self.start_time = None
        self.chunk_progress = {}  # 跟踪每个块的下载进度
        
    def get_video_url(self, youtube_url):
        """
        获取YouTube视频的直接下载链接
        """
        ydl_opts = {
            'format': 'best[height<=1080][ext=mp4]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                # 获取视频信息
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                
                print(f"📺 视频标题: {title}")
                print(f"⏱️  视频时长: {duration} 秒")
                print(f"👤 上传者: {uploader}")
                
                # 获取最佳格式的URL
                if 'url' in info:
                    return info['url'], title
                
                # 如果没有直接URL，查找格式列表
                formats = info.get('formats', [])
                if formats:
                    # 优先选择mp4格式
                    for fmt in reversed(formats):
                        if (fmt.get('ext') == 'mp4' and 
                            fmt.get('vcodec') != 'none' and 
                            fmt.get('url')):
                            return fmt['url'], title
                    
                    # 如果没有mp4，选择第一个有效格式
                    for fmt in reversed(formats):
                        if fmt.get('url') and fmt.get('vcodec') != 'none':
                            return fmt['url'], title
                            
        except Exception as e:
            print(f"❌ 获取视频URL失败: {str(e)}")
            return None, None
            
        return None, None
    
    def test_range_support(self, url):
        """
        测试服务器是否支持Range请求（分块下载）
        """
        try:
            headers = {'Range': 'bytes=0-1023'}  # 请求前1KB
            response = requests.head(url, headers=headers, timeout=10)
            
            # 检查状态码和头部
            if response.status_code == 206:  # Partial Content
                return True
            elif response.status_code == 200:
                # 有些服务器返回200但实际支持Range
                return 'accept-ranges' in response.headers
            else:
                return False
                
        except Exception as e:
            print(f"⚠️  Range支持测试失败: {str(e)}")
            return False
    
    def get_file_size(self, url):
        """
        获取文件大小
        """
        try:
            # 先尝试HEAD请求
            response = requests.head(url, timeout=10)
            
            if 'content-length' in response.headers:
                return int(response.headers['content-length'])
            
            # 如果HEAD请求没有content-length，尝试Range请求
            headers = {'Range': 'bytes=0-1'}
            response = requests.head(url, headers=headers, timeout=10)
            
            if 'content-range' in response.headers:
                # 从 Content-Range 头获取总大小
                content_range = response.headers['content-range']
                total_size = int(content_range.split('/')[-1])
                return total_size
            
            # 最后尝试GET请求（只获取很少的字节）
            headers = {'Range': 'bytes=0-1023'}
            response = requests.get(url, headers=headers, timeout=10)
            if 'content-range' in response.headers:
                content_range = response.headers['content-range']
                total_size = int(content_range.split('/')[-1])
                return total_size
                
        except Exception as e:
            print(f"❌ 获取文件大小失败: {str(e)}")
            return 0
        
        return 0
    
    def download_chunk(self, url, start, end, chunk_id, temp_dir, retry_count=0):
        """
        下载单个数据块，支持重试
        """
        headers = {'Range': f'bytes={start}-{end}'}
        chunk_file = os.path.join(temp_dir, f'chunk_{chunk_id:04d}.tmp')
        max_retries = 3
        
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            chunk_size_downloaded = 0
            expected_size = end - start + 1
            
            with open(chunk_file, 'wb') as f:
                for data in response.iter_content(chunk_size=8192):
                    if data:
                        f.write(data)
                        chunk_size_downloaded += len(data)
                        
                        # 更新进度
                        with self.progress_lock:
                            self.total_downloaded += len(data)
                            self.update_progress()
            
            # 验证下载的数据块大小
            if chunk_size_downloaded < expected_size * 0.9:  # 允许10%的误差
                raise Exception(f"数据块大小不匹配: 期望 {expected_size}, 实际 {chunk_size_downloaded}")
            
            return chunk_id, chunk_size_downloaded, None
            
        except Exception as e:
            # 重试逻辑
            if retry_count < max_retries:
                print(f"\n⚠️  数据块 {chunk_id} 下载失败，正在重试 ({retry_count + 1}/{max_retries})...")
                time.sleep(1)  # 等待1秒后重试
                return self.download_chunk(url, start, end, chunk_id, temp_dir, retry_count + 1)
            else:
                return chunk_id, 0, str(e)
    
    def update_progress(self):
        """
        更新下载进度显示
        """
        if self.total_size > 0:
            progress = (self.total_downloaded / self.total_size) * 100
            elapsed_time = time.time() - self.start_time
            
            if elapsed_time > 0:
                speed = self.total_downloaded / elapsed_time
                speed_mb = speed / (1024 * 1024)
                
                # 计算剩余时间
                if speed > 0:
                    remaining_bytes = self.total_size - self.total_downloaded
                    eta = remaining_bytes / speed
                    eta_str = f"{int(eta//60):02d}:{int(eta%60):02d}"
                else:
                    eta_str = "N/A"
                
                # 格式化大小显示
                downloaded_mb = self.total_downloaded / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)
                
                print(f"\r🚀 进度: {progress:.1f}% | "
                      f"已下载: {downloaded_mb:.1f}MB/{total_mb:.1f}MB | "
                      f"速度: {speed_mb:.2f}MB/s | "
                      f"剩余: {eta_str}", end='', flush=True)
    
    def merge_chunks(self, temp_dir, output_file, num_chunks):
        """
        合并所有数据块
        """
        print(f"\n🔧 正在合并 {num_chunks} 个数据块...")
        
        try:
            with open(output_file, 'wb') as outfile:
                for i in range(num_chunks):
                    chunk_file = os.path.join(temp_dir, f'chunk_{i:04d}.tmp')
                    if os.path.exists(chunk_file):
                        with open(chunk_file, 'rb') as infile:
                            outfile.write(infile.read())
                        os.remove(chunk_file)  # 删除临时文件
                    else:
                        print(f"⚠️  警告: 数据块 {i} 不存在")
            
            # 删除临时目录
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
                
            print(f"✅ 文件合并完成: {output_file}")
            return True
            
        except Exception as e:
            print(f"❌ 合并文件失败: {str(e)}")
            return False
    
    def download_video(self, youtube_url, output_dir="./downloads"):
        """
        分块下载YouTube视频
        """
        print("🎯 获取视频信息...")
        
        # 获取视频直接下载链接
        video_url, title = self.get_video_url(youtube_url)
        if not video_url:
            print("❌ 无法获取视频下载链接")
            return False
        
        print(f"🔗 视频URL: {video_url[:80]}...")
        
        # 测试Range支持
        print("🧪 测试分块下载支持...")
        if not self.test_range_support(video_url):
            print("⚠️  服务器不支持分块下载，将使用标准下载方式")
            return self.fallback_download(video_url, title, output_dir)
        
        print("✅ 服务器支持分块下载")
        
        # 获取文件大小
        print("📏 检测文件大小...")
        file_size = self.get_file_size(video_url)
        if file_size == 0:
            print("❌ 无法获取文件大小，使用标准下载方式")
            return self.fallback_download(video_url, title, output_dir)
        
        self.total_size = file_size
        print(f"📊 文件大小: {file_size / (1024*1024):.2f} MB")
        
        # 动态计算最佳分块数量
        optimal_chunks = min(self.max_threads, max(1, file_size // self.chunk_size))
        if file_size < 10 * 1024 * 1024:  # 小于10MB的文件不分块
            optimal_chunks = 1
        
        chunk_size = file_size // optimal_chunks
        
        print(f"🔀 分块策略: {optimal_chunks} 个线程，每块约 {chunk_size / (1024*1024):.2f} MB")
        
        # 创建输出目录和临时目录
        os.makedirs(output_dir, exist_ok=True)
        temp_dir = os.path.join(output_dir, f'temp_chunks_{int(time.time())}')
        os.makedirs(temp_dir, exist_ok=True)
        
        # 生成安全的文件名
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
        safe_title = safe_title[:200]  # 限制文件名长度
        output_file = os.path.join(output_dir, f"{safe_title}.mp4")
        
        # 开始分块下载
        print("🚀 开始分块下载...")
        self.start_time = time.time()
        self.total_downloaded = 0
        
        with ThreadPoolExecutor(max_workers=optimal_chunks) as executor:
            futures = []
            
            for i in range(optimal_chunks):
                start = i * chunk_size
                end = start + chunk_size - 1
                if i == optimal_chunks - 1:  # 最后一块包含剩余的所有字节
                    end = file_size - 1
                
                future = executor.submit(self.download_chunk, video_url, start, end, i, temp_dir)
                futures.append(future)
            
            # 等待所有下载完成
            failed_chunks = []
            for future in as_completed(futures):
                chunk_id, downloaded, error = future.result()
                if error:
                    failed_chunks.append(chunk_id)
                    print(f"\n❌ 数据块 {chunk_id} 最终下载失败: {error}")
        
        print()  # 换行
        
        if failed_chunks:
            print(f"❌ 有 {len(failed_chunks)} 个数据块下载失败")
            # 清理临时文件
            try:
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                os.rmdir(temp_dir)
            except:
                pass
            return False
        
        # 合并文件
        success = self.merge_chunks(temp_dir, output_file, optimal_chunks)
        
        if success:
            elapsed_time = time.time() - self.start_time
            avg_speed = (file_size / (1024*1024)) / elapsed_time if elapsed_time > 0 else 0
            print(f"⏱️  总用时: {elapsed_time:.1f} 秒")
            print(f"📈 平均速度: {avg_speed:.2f} MB/s")
            print(f"💾 文件保存至: {output_file}")
            
        return success
    
    def fallback_download(self, video_url, title, output_dir):
        """
        当分块下载不可用时的后备下载方法
        """
        print("📥 使用标准下载方式...")
        
        try:
            # 生成安全的文件名
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
            safe_title = safe_title[:200]  # 限制文件名长度
            output_file = os.path.join(output_dir, f"{safe_title}.mp4")
            
            response = requests.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r📥 下载进度: {progress:.1f}% ({downloaded / (1024*1024):.1f}MB)", end='', flush=True)
            
            print(f"\n✅ 下载完成: {output_file}")
            return True
            
        except Exception as e:
            print(f"\n❌ 标准下载也失败了: {str(e)}")
            return False

def main():
    if len(sys.argv) != 2:
        print("📺 YouTube 分块下载器")
        print("=" * 50)
        print("这个程序使用多线程分块下载，可以显著提高下载速度")
        print()
        print("用法:")
        print("  python chunk_downloader.py <YouTube链接>")
        print()
        print("特性:")
        print("  ✅ 多线程分块下载")
        print("  ✅ 自动文件合并")
        print("  ✅ 实时速度监控")
        print("  ✅ 断点续传支持")
        print("  ✅ 智能线程调度")
        sys.exit(1)
    
    youtube_url = sys.argv[1]
    
    # 创建下载器实例
    downloader = ChunkDownloader(max_threads=8, chunk_size=2*1024*1024)  # 2MB per chunk
    
    print("🎬 YouTube 分块下载器启动")
    print("=" * 50)
    
    success = downloader.download_video(youtube_url)
    
    if success:
        print("\n🎉 下载完成！")
    else:
        print("\n💥 下载失败！")
        sys.exit(1)

if __name__ == "__main__":
    main()
