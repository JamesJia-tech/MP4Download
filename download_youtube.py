import sys
import yt_dlp

def download_video(url):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def main():
    if len(sys.argv) != 2:
        print("用法: python download_youtube.py <YouTube链接>")
        sys.exit(1)
    url = sys.argv[1]
    download_video(url)

if __name__ == "__main__":
    main()
