#!/usr/bin/env python3
"""
分块下载演示程序
使用支持Range请求的测试文件来演示分块下载的工作原理
"""

import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import argparse

class ChunkDownloadDemo:
    def __init__(self, max_threads=4, chunk_size=1024*1024):
        self.max_threads = max_threads
        self.chunk_size = chunk_size
        self.progress_lock = threading.Lock()
        self.total_downloaded = 0
        self.total_size = 0
        self.start_time = None
        self.chunk_progress = {}
        
    def test_url_support(self, url):
        """测试URL是否支持Range请求"""
        try:
            headers = {'Range': 'bytes=0-1023'}
            response = requests.head(url, headers=headers, timeout=10)
            
            if response.status_code == 206:
                print(f"✅ 服务器支持Range请求 (状态码: {response.status_code})")
                return True
            elif response.status_code == 200:
                support = 'accept-ranges' in response.headers
                if support:
                    print(f"✅ 服务器支持Range请求 (Accept-Ranges: {response.headers.get('accept-ranges')})")
                else:
                    print(f"❌ 服务器不支持Range请求")
                return support
            else:
                print(f"❌ 服务器不支持Range请求 (状态码: {response.status_code})")
                return False
                
        except Exception as e:
            print(f"❌ 测试Range支持失败: {str(e)}")
            return False
    
    def get_file_size(self, url):
        """获取文件大小"""
        try:
            response = requests.head(url, timeout=10)
            
            if 'content-length' in response.headers:
                size = int(response.headers['content-length'])
                print(f"📊 文件大小: {size / (1024*1024):.2f} MB ({size:,} 字节)")
                return size
            else:
                print("❌ 无法获取文件大小")
                return 0
                
        except Exception as e:
            print(f"❌ 获取文件大小失败: {str(e)}")
            return 0
    
    def download_chunk(self, url, start, end, chunk_id, temp_dir):
        """下载单个数据块"""
        headers = {'Range': f'bytes={start}-{end}'}
        chunk_file = os.path.join(temp_dir, f'chunk_{chunk_id:04d}.tmp')
        
        print(f"🔄 线程 {chunk_id}: 开始下载字节 {start:,} - {end:,}")
        
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
            
            actual_size = os.path.getsize(chunk_file)
            print(f"✅ 线程 {chunk_id}: 完成，下载 {actual_size:,} 字节")
            
            return chunk_id, chunk_size_downloaded, None
            
        except Exception as e:
            print(f"❌ 线程 {chunk_id}: 失败 - {str(e)}")
            return chunk_id, 0, str(e)
    
    def update_progress(self):
        """更新下载进度"""
        if self.total_size > 0:
            progress = (self.total_downloaded / self.total_size) * 100
            elapsed_time = time.time() - self.start_time
            
            if elapsed_time > 0:
                speed = self.total_downloaded / elapsed_time
                speed_mb = speed / (1024 * 1024)
                
                downloaded_mb = self.total_downloaded / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)
                
                progress_bar = self.get_progress_bar(progress)
                
                print(f"\r{progress_bar} {progress:.1f}% | "
                      f"{downloaded_mb:.1f}MB/{total_mb:.1f}MB | "
                      f"{speed_mb:.2f}MB/s", end='', flush=True)
    
    def get_progress_bar(self, progress, width=20):
        """生成进度条"""
        filled = int(width * progress / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"
    
    def merge_chunks(self, temp_dir, output_file, num_chunks):
        """合并所有数据块"""
        print(f"\n🔧 开始合并 {num_chunks} 个数据块...")
        
        try:
            total_merged = 0
            with open(output_file, 'wb') as outfile:
                for i in range(num_chunks):
                    chunk_file = os.path.join(temp_dir, f'chunk_{i:04d}.tmp')
                    if os.path.exists(chunk_file):
                        chunk_size = os.path.getsize(chunk_file)
                        print(f"📄 合并数据块 {i}: {chunk_size:,} 字节")
                        
                        with open(chunk_file, 'rb') as infile:
                            data = infile.read()
                            outfile.write(data)
                            total_merged += len(data)
                        
                        os.remove(chunk_file)
                    else:
                        print(f"⚠️  数据块 {i} 不存在")
            
            # 清理临时目录
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
            
            print(f"✅ 合并完成: {output_file}")
            print(f"📦 合并后文件大小: {total_merged:,} 字节 ({total_merged/(1024*1024):.2f} MB)")
            
            return True
            
        except Exception as e:
            print(f"❌ 合并失败: {str(e)}")
            return False
    
    def download_file(self, url, output_file):
        """分块下载文件"""
        print("🎯 开始分块下载演示")
        print("=" * 60)
        
        # 测试Range支持
        print("🧪 测试服务器Range支持...")
        if not self.test_url_support(url):
            print("❌ 服务器不支持分块下载")
            return False
        
        # 获取文件大小
        print("\n📏 获取文件信息...")
        file_size = self.get_file_size(url)
        if file_size == 0:
            print("❌ 无法获取文件大小")
            return False
        
        self.total_size = file_size
        
        # 计算分块策略
        num_chunks = min(self.max_threads, max(1, file_size // self.chunk_size))
        chunk_size = file_size // num_chunks
        
        print(f"\n🔀 分块策略:")
        print(f"   总线程数: {num_chunks}")
        print(f"   每块大小: {chunk_size:,} 字节 ({chunk_size/(1024*1024):.2f} MB)")
        
        # 创建临时目录
        temp_dir = os.path.join(os.path.dirname(output_file), f'temp_chunks_{int(time.time())}')
        os.makedirs(temp_dir, exist_ok=True)
        
        print(f"\n🚀 开始多线程下载...")
        print("=" * 60)
        
        self.start_time = time.time()
        self.total_downloaded = 0
        
        # 显示每个线程的分工
        for i in range(num_chunks):
            start = i * chunk_size
            end = start + chunk_size - 1
            if i == num_chunks - 1:
                end = file_size - 1
            print(f"🧵 线程 {i}: 字节 {start:,} - {end:,} ({end-start+1:,} 字节)")
        
        print()
        
        # 启动多线程下载
        with ThreadPoolExecutor(max_workers=num_chunks) as executor:
            futures = []
            
            for i in range(num_chunks):
                start = i * chunk_size
                end = start + chunk_size - 1
                if i == num_chunks - 1:
                    end = file_size - 1
                
                future = executor.submit(self.download_chunk, url, start, end, i, temp_dir)
                futures.append(future)
            
            # 等待所有下载完成
            failed_chunks = []
            for future in as_completed(futures):
                chunk_id, downloaded, error = future.result()
                if error:
                    failed_chunks.append(chunk_id)
        
        print()  # 换行
        
        if failed_chunks:
            print(f"❌ 有 {len(failed_chunks)} 个数据块下载失败")
            return False
        
        # 合并文件
        success = self.merge_chunks(temp_dir, output_file, num_chunks)
        
        if success:
            elapsed_time = time.time() - self.start_time
            avg_speed = (file_size / (1024*1024)) / elapsed_time if elapsed_time > 0 else 0
            
            print("\n" + "=" * 60)
            print("🎉 分块下载演示完成!")
            print(f"⏱️  总用时: {elapsed_time:.2f} 秒")
            print(f"📈 平均速度: {avg_speed:.2f} MB/s")
            print(f"💾 文件位置: {output_file}")
            
            # 验证文件完整性
            actual_size = os.path.getsize(output_file)
            if actual_size == file_size:
                print("✅ 文件完整性验证通过")
            else:
                print(f"⚠️  文件大小不匹配: 期望 {file_size:,}, 实际 {actual_size:,}")
        
        return success

def main():
    parser = argparse.ArgumentParser(description="分块下载演示程序")
    parser.add_argument('url', nargs='?', 
                       default='https://httpbin.org/bytes/10485760',  # 10MB测试文件
                       help='要下载的文件URL (默认: httpbin 10MB测试文件)')
    parser.add_argument('--output', '-o', default='./downloads/demo_file.bin',
                       help='输出文件路径')
    parser.add_argument('--threads', '-t', type=int, default=4,
                       help='线程数 (默认: 4)')
    parser.add_argument('--chunk-size', '-c', type=int, default=1,
                       help='数据块大小 MB (默认: 1)')
    
    args = parser.parse_args()
    
    # 一些推荐的测试URL
    test_urls = {
        'httpbin_10mb': 'https://httpbin.org/bytes/10485760',  # 10MB
        'httpbin_5mb': 'https://httpbin.org/bytes/5242880',    # 5MB
        'httpbin_1mb': 'https://httpbin.org/bytes/1048576',    # 1MB
    }
    
    print("🧪 分块下载演示程序")
    print("=" * 60)
    print("这个程序演示如何将大文件分成多个块并行下载")
    print(f"🔧 配置: {args.threads} 线程, {args.chunk_size}MB 块大小")
    print(f"📁 输出文件: {args.output}")
    print(f"🌐 下载URL: {args.url}")
    
    if args.url in test_urls.values():
        print("📝 使用测试URL，这个URL支持Range请求")
    
    print("=" * 60)
    
    # 创建输出目录
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # 创建下载器
    downloader = ChunkDownloadDemo(
        max_threads=args.threads,
        chunk_size=args.chunk_size * 1024 * 1024
    )
    
    # 开始下载
    success = downloader.download_file(args.url, args.output)
    
    if not success:
        print("\n💥 演示失败！")
        sys.exit(1)
    else:
        print("\n🎊 演示成功完成！")

if __name__ == "__main__":
    main()
