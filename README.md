# downMP4 - YouTube 高速下载器

一个功能强大的命令行Python脚本，支持高速多线程下载YouTube视频。

## ✨ 功能特性

- 🚀 **多线程并发下载** - 支持片段并发下载，大幅提升下载速度
- 📱 **多视频批量下载** - 一次性下载多个视频
- 🔄 **智能重试机制** - 自动重试失败的下载
- 📊 **实时进度显示** - 显示下载进度、速度和剩余时间
- 📋 **视频信息查看** - 预览视频信息而不下载
- 🎯 **智能质量选择** - 自动选择最佳画质（最高1080p）
- 📁 **自动目录管理** - 自动创建下载目录

## 🚀 快速开始

### 安装依赖
```bash
pip install yt-dlp
```

### 基本用法

#### 下载单个视频
```bash
python download_youtube.py https://www.youtube.com/watch?v=VIDEO_ID
```

#### 下载多个视频（并发）
```bash
python download_youtube.py URL1 URL2 URL3
```

#### 查看视频信息
```bash
python download_youtube.py --info https://www.youtube.com/watch?v=VIDEO_ID
```

## ⚙️ 性能优化

- **并发片段下载**: 4个并发连接
- **Chunk大小**: 10MB
- **重试机制**: 自动重试10次
- **指数退避**: 智能重试间隔

## 📁 文件结构

```
./downloads/
├── video_1/          # 第一个视频
├── video_2/          # 第二个视频
└── ...
```

## 🎯 VS Code 集成

使用VS Code任务快速下载：

1. **单视频下载**: `Cmd+Shift+P` → "Tasks: Run Task" → "Run YouTube Downloader"
2. **视频信息**: `Cmd+Shift+P` → "Tasks: Run Task" → "Get Video Info"
3. **批量下载**: `Cmd+Shift+P` → "Tasks: Run Task" → "Download Multiple Videos"

## 📋 系统要求

- Python 3.7+
- yt-dlp
- ffmpeg (用于合并音视频)

## ⚠️ 免责声明

本项目仅用于学习和个人用途，请勿用于任何非法用途。请遵守YouTube的服务条款和当地法律法规。
