import os
import tempfile
import yt_dlp

def download_youtube_video(url, filename=None):
    temp_dir = tempfile.gettempdir()
    
    # If a filename is provided, force yt-dlp to use it
    if filename:
        # Ensure we don't accidentally append double extensions
        base, _ = os.path.splitext(filename)
        outtmpl = os.path.join(temp_dir, f"{base}.%(ext)s")
    else:
        # Otherwise, let yt-dlp name it based on the video title
        outtmpl = os.path.join(temp_dir, '%(title)s.%(ext)s')

    # Applying the same logic from your working GitHub Action:
    # 1. Route through the local Cloudflare WARP SOCKS5 proxy
    # 2. Spoof Android/iOS clients to bypass bot blocks
    # 3. Merge best video and audio into an mp4 container
    ydl_opts = {
        'proxy': 'socks5://127.0.0.1:40000',
        'extractor_args': {
            'youtube': {
                # tv_embedded + web are not affected by the SABR-only experiment
                # that blocks URL extraction on ios/android clients.
                # See: https://github.com/yt-dlp/yt-dlp/issues/12482
                'player_client': ['tv_embedded', 'web'],
            }
        },
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'outtmpl': outtmpl,
        'quiet': False,
        'no_warnings': False,
    }
    
    try:
        print(f"\n[+] Downloading YouTube video via yt-dlp: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info and download
            info_dict = ydl.extract_info(url, download=True)
            
            # yt-dlp returns the path it downloaded to
            downloaded_file_path = ydl.prepare_filename(info_dict)
            
            # Because of the merge_output_format='mp4', the final file might 
            # have its extension changed from the prepare_filename prediction.
            # Let's verify the actual final path.
            base_path, _ = os.path.splitext(downloaded_file_path)
            mp4_path = f"{base_path}.mp4"
            
            if not os.path.exists(downloaded_file_path) and os.path.exists(mp4_path):
                downloaded_file_path = mp4_path
                
            print(f"[✔] Download and merge completed: {downloaded_file_path}")
            return downloaded_file_path

    except Exception as e:
        print(f"[-] An error occurred during YouTube download: {e}")
        raise
