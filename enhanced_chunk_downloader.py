#!/usr/bin/env python3
"""
高性能 YouTube 分块下载器
支持多线程并发下载，自动重试，智能分块策略
"""

import os
import sys
import time
import math
import threading
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import yt_dlp
from urllib.parse import urlparse
import argparse
from config import DOWNLOAD_CONFIG, VIDEO_CONFIG, FILE_CONFIG, NETWORK_CONFIG, PROGRESS_CONFIG

class EnhancedChunkDownloader:
    def __init__(self, config=None):
        self.config = config or DOWNLOAD_CONFIG
        self.video_config = VIDEO_CONFIG
        self.file_config = FILE_CONFIG
        self.network_config = NETWORK_CONFIG
        self.progress_config = PROGRESS_CONFIG
        
        self.max_threads = self.config.get('max_threads', 8)
        self.chunk_size = self.config.get('chunk_size', 2*1024*1024)
        
        self.progress_lock = threading.Lock()
        self.total_downloaded = 0
        self.total_size = 0
        self.start_time = None
        self.last_update_time = 0
        
        # 配置requests会话
        self.session = requests.Session()
        if self.network_config.get('user_agent'):
            self.session.headers.update({
                'User-Agent': self.network_config['user_agent']
            })
    
    def get_video_info(self, youtube_url):
        """
        获取视频信息和最佳下载URL
        """
        format_string = "/".join(self.video_config['format_priority'])
        
        ydl_opts = {
            'format': format_string,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown')
                file_size = info.get('filesize') or info.get('filesize_approx', 0)
                
                print(f"📺 视频标题: {title}")
                print(f"⏱️  视频时长: {self.format_duration(duration)}")
                print(f"👤 上传者: {uploader}")
                if file_size:
                    print(f"📊 预估大小: {file_size / (1024*1024):.2f} MB")
                
                # 获取下载URL
                url = info.get('url')
                if not url and 'formats' in info:
                    # 从格式列表中选择最佳格式
                    formats = info['formats']
                    for fmt in reversed(formats):
                        if fmt.get('url') and fmt.get('vcodec') != 'none':
                            url = fmt['url']
                            file_size = fmt.get('filesize') or file_size
                            break
                
                return {
                    'url': url,
                    'title': title,
                    'duration': duration,
                    'uploader': uploader,
                    'filesize': file_size,
                    'info': info
                }
                
        except Exception as e:
            print(f"❌ 获取视频信息失败: {str(e)}")
            return None
    
    def format_duration(self, seconds):
        """格式化时长显示"""
        if not seconds:
            return "未知"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def test_range_support(self, url):
        """测试服务器是否支持Range请求"""
        try:
            headers = {'Range': 'bytes=0-1023'}
            response = self.session.head(url, headers=headers, timeout=10)
            
            if response.status_code == 206:
                return True
            elif response.status_code == 200:
                return 'accept-ranges' in response.headers
            else:
                return False
                
        except Exception as e:
            print(f"⚠️  Range支持测试失败: {str(e)}")
            return False
    
    def get_accurate_file_size(self, url):
        """获取精确的文件大小"""
        try:
            # 方法1: HEAD请求
            response = self.session.head(url, timeout=10)
            if 'content-length' in response.headers:
                return int(response.headers['content-length'])
            
            # 方法2: Range请求获取
            headers = {'Range': 'bytes=0-1'}
            response = self.session.head(url, headers=headers, timeout=10)
            if 'content-range' in response.headers:
                content_range = response.headers['content-range']
                total_size = int(content_range.split('/')[-1])
                return total_size
            
            # 方法3: 小范围GET请求
            headers = {'Range': 'bytes=0-1023'}
            response = self.session.get(url, headers=headers, timeout=10)
            if 'content-range' in response.headers:
                content_range = response.headers['content-range']
                total_size = int(content_range.split('/')[-1])
                return total_size
                
        except Exception as e:
            print(f"❌ 获取文件大小失败: {str(e)}")
            return 0
        
        return 0
    
    def calculate_optimal_chunks(self, file_size):
        """计算最佳分块策略"""
        if file_size < self.config.get('small_file_threshold', 10*1024*1024):
            return 1
        
        # 基于文件大小和网络条件动态调整
        optimal_chunks = min(
            self.max_threads,
            max(1, file_size // self.chunk_size),
            16  # 最大不超过16个块
        )
        
        return optimal_chunks
    
    def download_chunk(self, url, start, end, chunk_id, temp_dir, retry_count=0):
        """下载单个数据块，支持重试"""
        headers = {'Range': f'bytes={start}-{end}'}
        chunk_file = os.path.join(temp_dir, f'chunk_{chunk_id:04d}.tmp')
        max_retries = self.config.get('max_retries', 3)
        timeout = self.config.get('timeout', 30)
        
        try:
            response = self.session.get(url, headers=headers, stream=True, timeout=timeout)
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
                            current_time = time.time()
                            if (current_time - self.last_update_time) > self.progress_config.get('update_interval', 0.5):
                                self.update_progress()
                                self.last_update_time = current_time
            
            # 验证下载完整性
            if chunk_size_downloaded < expected_size * 0.95:  # 允许5%的误差
                raise Exception(f"数据块不完整: 期望 {expected_size}, 实际 {chunk_size_downloaded}")
            
            return chunk_id, chunk_size_downloaded, None
            
        except Exception as e:
            # 重试逻辑
            if retry_count < max_retries:
                wait_time = min(2 ** retry_count, 10)  # 指数退避，最大10秒
                print(f"\n⚠️  数据块 {chunk_id} 下载失败，{wait_time}秒后重试 ({retry_count + 1}/{max_retries})")
                time.sleep(wait_time)
                return self.download_chunk(url, start, end, chunk_id, temp_dir, retry_count + 1)
            else:
                return chunk_id, 0, str(e)
    
    def update_progress(self):
        """更新下载进度显示"""
        if not self.progress_config.get('verbose', True):
            return
            
        if self.total_size > 0:
            progress = (self.total_downloaded / self.total_size) * 100
            elapsed_time = time.time() - self.start_time
            
            progress_bar = self.get_progress_bar(progress)
            
            if elapsed_time > 0:
                speed = self.total_downloaded / elapsed_time
                speed_mb = speed / (1024 * 1024)
                
                # 计算ETA
                if speed > 0:
                    remaining_bytes = self.total_size - self.total_downloaded
                    eta = remaining_bytes / speed
                    eta_str = self.format_time(eta)
                else:
                    eta_str = "N/A"
                
                # 格式化显示
                downloaded_mb = self.total_downloaded / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)
                
                status = f"\r{progress_bar} {progress:.1f}% | "
                status += f"{downloaded_mb:.1f}MB/{total_mb:.1f}MB"
                
                if self.progress_config.get('show_speed', True):
                    status += f" | {speed_mb:.2f}MB/s"
                
                if self.progress_config.get('show_eta', True):
                    status += f" | ETA: {eta_str}"
                
                print(status, end='', flush=True)
    
    def get_progress_bar(self, progress, width=30):
        """生成进度条"""
        filled = int(width * progress / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"
    
    def format_time(self, seconds):
        """格式化时间显示"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds//60)}m{int(seconds%60)}s"
        else:
            return f"{int(seconds//3600)}h{int((seconds%3600)//60)}m"
    
    def merge_chunks(self, temp_dir, output_file, num_chunks):
        """合并所有数据块"""
        print(f"\n🔧 正在合并 {num_chunks} 个数据块...")
        
        try:
            with open(output_file, 'wb') as outfile:
                for i in range(num_chunks):
                    chunk_file = os.path.join(temp_dir, f'chunk_{i:04d}.tmp')
                    if os.path.exists(chunk_file):
                        with open(chunk_file, 'rb') as infile:
                            while True:
                                chunk = infile.read(64*1024)  # 64KB 块读取
                                if not chunk:
                                    break
                                outfile.write(chunk)
                        os.remove(chunk_file)
                        
                        # 显示合并进度
                        progress = ((i + 1) / num_chunks) * 100
                        print(f"\r🔧 合并进度: {progress:.1f}%", end='', flush=True)
                    else:
                        print(f"\n⚠️  警告: 数据块 {i} 不存在")
            
            # 清理临时目录
            try:
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)
            except:
                pass
                
            print(f"\n✅ 文件合并完成: {output_file}")
            return True
            
        except Exception as e:
            print(f"\n❌ 合并文件失败: {str(e)}")
            return False
    
    def generate_filename(self, title, video_id=None):
        """生成安全的文件名"""
        # 清理非法字符
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_', '.', '(', ')')).strip()
        
        # 限制长度
        max_length = self.file_config.get('max_filename_length', 200)
        if len(safe_title) > max_length - 20:  # 为扩展名和ID预留空间
            safe_title = safe_title[:max_length-20]
        
        # 添加视频ID（如果启用）
        if self.file_config.get('include_video_id', True) and video_id:
            safe_title += f" [{video_id}]"
        
        return f"{safe_title}.mp4"
    
    def cleanup_failed_download(self, temp_dir):
        """清理失败的下载临时文件"""
        if not self.file_config.get('auto_cleanup', True):
            return
            
        try:
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, file))
                os.rmdir(temp_dir)
                print("🧹 已清理临时文件")
        except Exception as e:
            print(f"⚠️  清理临时文件失败: {str(e)}")
    
    def download_video(self, youtube_url, output_dir=None):
        """主下载函数"""
        output_dir = output_dir or self.file_config.get('default_output_dir', './downloads')
        
        print("🎯 分析视频信息...")
        
        # 获取视频信息
        video_info = self.get_video_info(youtube_url)
        if not video_info or not video_info['url']:
            print("❌ 无法获取视频下载链接")
            return False
        
        video_url = video_info['url']
        title = video_info['title']
        
        print(f"🔗 视频URL: {video_url[:80]}...")
        
        # 检查分块下载支持
        if not self.config.get('enable_chunked_download', True):
            print("📥 分块下载已禁用，使用标准下载")
            return self.fallback_download(video_url, title, output_dir)
        
        print("🧪 测试分块下载支持...")
        if not self.test_range_support(video_url):
            print("⚠️  服务器不支持分块下载，切换到标准模式")
            return self.fallback_download(video_url, title, output_dir)
        
        print("✅ 服务器支持分块下载")
        
        # 获取精确文件大小
        print("📏 获取文件大小...")
        file_size = self.get_accurate_file_size(video_url)
        if file_size == 0:
            # 使用预估大小
            file_size = video_info.get('filesize', 0)
            if file_size == 0:
                print("❌ 无法获取文件大小，使用标准下载")
                return self.fallback_download(video_url, title, output_dir)
            print(f"📊 使用预估大小: {file_size / (1024*1024):.2f} MB")
        else:
            print(f"📊 文件大小: {file_size / (1024*1024):.2f} MB")
        
        self.total_size = file_size
        
        # 计算最佳分块策略
        optimal_chunks = self.calculate_optimal_chunks(file_size)
        chunk_size = file_size // optimal_chunks
        
        print(f"🔀 分块策略: {optimal_chunks} 个线程，每块约 {chunk_size / (1024*1024):.2f} MB")
        
        # 准备文件路径
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time())
        temp_dir = os.path.join(output_dir, f"{self.file_config['temp_dir_prefix']}{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        filename = self.generate_filename(title, video_info['info'].get('id'))
        output_file = os.path.join(output_dir, filename)
        
        # 开始分块下载
        print("🚀 开始分块下载...")
        print("=" * 60)
        
        self.start_time = time.time()
        self.total_downloaded = 0
        self.last_update_time = 0
        
        with ThreadPoolExecutor(max_workers=optimal_chunks) as executor:
            futures = []
            
            for i in range(optimal_chunks):
                start = i * chunk_size
                end = start + chunk_size - 1
                if i == optimal_chunks - 1:
                    end = file_size - 1
                
                future = executor.submit(self.download_chunk, video_url, start, end, i, temp_dir)
                futures.append(future)
            
            # 等待所有下载完成
            failed_chunks = []
            completed_chunks = 0
            
            for future in as_completed(futures):
                chunk_id, downloaded, error = future.result()
                completed_chunks += 1
                
                if error:
                    failed_chunks.append(chunk_id)
                    print(f"\n❌ 数据块 {chunk_id} 最终失败: {error}")
                else:
                    if self.progress_config.get('verbose'):
                        print(f"\n✅ 数据块 {chunk_id} 完成 ({completed_chunks}/{optimal_chunks})")
        
        print()  # 换行
        
        if failed_chunks:
            print(f"❌ 有 {len(failed_chunks)} 个数据块下载失败")
            self.cleanup_failed_download(temp_dir)
            return False
        
        # 合并文件
        success = self.merge_chunks(temp_dir, output_file, optimal_chunks)
        
        if success:
            elapsed_time = time.time() - self.start_time
            avg_speed = (file_size / (1024*1024)) / elapsed_time if elapsed_time > 0 else 0
            
            print("=" * 60)
            print("🎉 下载完成!")
            print(f"⏱️  总用时: {self.format_time(elapsed_time)}")
            print(f"📈 平均速度: {avg_speed:.2f} MB/s")
            print(f"💾 文件位置: {output_file}")
            print(f"📦 文件大小: {os.path.getsize(output_file) / (1024*1024):.2f} MB")
        
        return success
    
    def fallback_download(self, video_url, title, output_dir):
        """标准下载方法"""
        print("📥 使用标准下载模式...")
        
        try:
            filename = self.generate_filename(title)
            output_file = os.path.join(output_dir, filename)
            
            response = self.session.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            start_time = time.time()
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            elapsed = time.time() - start_time
                            speed = (downloaded / (1024*1024)) / elapsed if elapsed > 0 else 0
                            
                            print(f"\r📥 {progress:.1f}% | {downloaded/(1024*1024):.1f}MB | {speed:.2f}MB/s", 
                                  end='', flush=True)
            
            print(f"\n✅ 下载完成: {output_file}")
            return True
            
        except Exception as e:
            print(f"\n❌ 标准下载失败: {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description="高性能 YouTube 分块下载器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "https://www.youtube.com/watch?v=VIDEO_ID"
  %(prog)s --threads 16 --chunk-size 5 "https://www.youtube.com/watch?v=VIDEO_ID"
  %(prog)s --output ./my_videos "https://www.youtube.com/watch?v=VIDEO_ID"
        """
    )
    
    parser.add_argument('url', help='YouTube视频链接')
    parser.add_argument('--threads', '-t', type=int, default=8, 
                       help='最大线程数 (默认: 8)')
    parser.add_argument('--chunk-size', '-c', type=int, default=2,
                       help='数据块大小 MB (默认: 2)')
    parser.add_argument('--output', '-o', default='./downloads',
                       help='输出目录 (默认: ./downloads)')
    parser.add_argument('--no-chunk', action='store_true',
                       help='禁用分块下载，使用标准模式')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='显示详细信息')
    
    args = parser.parse_args()
    
    # 自定义配置
    custom_config = DOWNLOAD_CONFIG.copy()
    custom_config['max_threads'] = args.threads
    custom_config['chunk_size'] = args.chunk_size * 1024 * 1024
    custom_config['enable_chunked_download'] = not args.no_chunk
    
    if args.verbose:
        PROGRESS_CONFIG['verbose'] = True
    
    print("🎬 高性能 YouTube 分块下载器")
    print("=" * 60)
    print(f"🔧 配置: {args.threads} 线程, {args.chunk_size}MB 块大小")
    print(f"📁 输出目录: {args.output}")
    print("=" * 60)
    
    # 创建下载器并开始下载
    downloader = EnhancedChunkDownloader(custom_config)
    success = downloader.download_video(args.url, args.output)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
