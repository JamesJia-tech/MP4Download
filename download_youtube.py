import sys
import os
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
import threading

def download_video(url, output_dir="./downloads"):
    """
    下载视频，支持多线程和高速下载
    """
    # 创建下载目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 优化的下载配置
    ydl_opts = {
        # 视频质量设置
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
        'merge_output_format': 'mp4',
        
        # 输出设置
        'outtmpl': os.path.join(output_dir, '%(title)s [%(id)s].%(ext)s'),
        
        # 多线程下载设置
        'concurrent_fragment_downloads': 4,  # 并发片段下载数
        'http_chunk_size': 10485760,         # 10MB chunk size
        
        # 网络优化
        'retries': 10,                       # 重试次数
        'fragment_retries': 10,              # 片段重试次数
        'retry_sleep_functions': {
            'http': lambda n: min(2 ** n, 30),  # 指数退避
            'fragment': lambda n: min(2 ** n, 30),
        },
        
        # 性能优化
        'writesubtitles': False,             # 不下载字幕以提高速度
        'writeautomaticsub': False,
        'writedescription': False,
        'writeinfojson': False,
        'writethumbnail': False,
        
        # 进度显示
        'progress_hooks': [progress_hook],
    }
    
    print(f"开始下载: {url}")
    print(f"保存目录: {output_dir}")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 先获取视频信息
            info = ydl.extract_info(url, download=False)
            print(f"视频标题: {info.get('title', 'Unknown')}")
            print(f"视频时长: {info.get('duration', 'Unknown')} 秒")
            print(f"上传者: {info.get('uploader', 'Unknown')}")
            
            # 开始下载
            ydl.download([url])
            print("✅ 下载完成!")
            
    except Exception as e:
        print(f"❌ 下载失败: {str(e)}")
        return False
    
    return True

def progress_hook(d):
    """
    下载进度回调函数
    """
    if d['status'] == 'downloading':
        # 显示下载进度
        percent = d.get('_percent_str', 'N/A')
        speed = d.get('_speed_str', 'N/A')
        eta = d.get('_eta_str', 'N/A')
        print(f"\r📥 下载中: {percent} | 速度: {speed} | 剩余时间: {eta}", end='', flush=True)
    elif d['status'] == 'finished':
        print(f"\n✅ 下载完成: {d['filename']}")

def download_multiple_videos(urls, max_workers=3):
    """
    并发下载多个视频
    """
    print(f"🚀 启动并发下载，最大线程数: {max_workers}")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, url in enumerate(urls, 1):
            output_dir = f"./downloads/video_{i}"
            future = executor.submit(download_video, url, output_dir)
            futures.append(future)
        
        # 等待所有下载完成
        for i, future in enumerate(futures, 1):
            try:
                result = future.result()
                if result:
                    print(f"✅ 视频 {i} 下载成功")
                else:
                    print(f"❌ 视频 {i} 下载失败")
            except Exception as e:
                print(f"❌ 视频 {i} 下载出错: {str(e)}")

def get_video_info(url):
    """
    获取视频信息而不下载
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 'Unknown'),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 'Unknown'),
                'upload_date': info.get('upload_date', 'Unknown'),
                'formats': len(info.get('formats', [])),
            }
    except Exception as e:
        print(f"❌ 获取视频信息失败: {str(e)}")
        return None

def main():
    if len(sys.argv) < 2:
        print("📺 YouTube 高速下载器")
        print("=" * 40)
        print("用法:")
        print("  单个视频: python download_youtube.py <YouTube链接>")
        print("  多个视频: python download_youtube.py <链接1> <链接2> ...")
        print("  查看信息: python download_youtube.py --info <YouTube链接>")
        print("\n功能特性:")
        print("  ✅ 多线程并发下载")
        print("  ✅ 自动重试机制")
        print("  ✅ 优化下载速度")
        print("  ✅ 实时进度显示")
        sys.exit(1)
    
    # 检查是否是查看信息模式
    if sys.argv[1] == '--info' and len(sys.argv) == 3:
        url = sys.argv[2]
        print("📋 获取视频信息...")
        info = get_video_info(url)
        if info:
            print("\n📺 视频信息:")
            print("=" * 40)
            for key, value in info.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
        return
    
    urls = sys.argv[1:]
    
    if len(urls) == 1:
        # 单个视频下载
        download_video(urls[0])
    else:
        # 多个视频并发下载
        download_multiple_videos(urls)

if __name__ == "__main__":
    main()
