# YouTube 分块下载器配置文件

# 下载配置
DOWNLOAD_CONFIG = {
    # 最大并发线程数 (建议: 4-16)
    "max_threads": 8,
    
    # 每个数据块的大小 (字节) 
    # 2MB = 2 * 1024 * 1024
    # 5MB = 5 * 1024 * 1024
    "chunk_size": 2 * 1024 * 1024,
    
    # 下载重试次数
    "max_retries": 3,
    
    # 请求超时时间 (秒)
    "timeout": 30,
    
    # 是否启用分块下载 (False时使用标准下载)
    "enable_chunked_download": True,
    
    # 小文件大小阈值 (小于此大小的文件不分块，字节)
    "small_file_threshold": 10 * 1024 * 1024,  # 10MB
}

# 视频质量配置
VIDEO_CONFIG = {
    # 视频格式优先级 (按顺序尝试)
    "format_priority": [
        "best[height<=1080][ext=mp4]",
        "best[ext=mp4]", 
        "best[height<=720][ext=mp4]",
        "best"
    ],
    
    # 是否下载音频
    "include_audio": True,
    
    # 视频质量上限 (可选: 720, 1080, 1440, 2160)
    "max_height": 1080,
}

# 文件配置
FILE_CONFIG = {
    # 默认下载目录
    "default_output_dir": "./downloads",
    
    # 文件名最大长度
    "max_filename_length": 200,
    
    # 是否包含视频ID在文件名中
    "include_video_id": True,
    
    # 临时文件目录前缀
    "temp_dir_prefix": "temp_chunks_",
    
    # 是否自动清理失败的临时文件
    "auto_cleanup": True,
}

# 网络配置
NETWORK_CONFIG = {
    # User-Agent
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    
    # 是否启用代理 (留空不使用代理)
    "proxy": "",
    
    # 连接池大小
    "pool_connections": 10,
    
    # 连接池最大大小
    "pool_maxsize": 10,
}

# 进度显示配置
PROGRESS_CONFIG = {
    # 进度更新间隔 (秒)
    "update_interval": 0.5,
    
    # 是否显示实时速度
    "show_speed": True,
    
    # 是否显示ETA
    "show_eta": True,
    
    # 是否显示详细信息
    "verbose": True,
}
