@echo off
yt-dlp --extractor-args "youtube:player_client=android" -x --audio-format mp3 --audio-quality 192K --embed-metadata --embed-thumbnail --convert-thumbnails jpg --min-sleep-interval 15 --max-sleep-interval 45 -o "%%(playlist_index)02d - %%(title)s.%%(ext)s" "https://youtube.com/playlist?list=PLBnJv6rImVe8jvtAr9X-YbRaGkEQXjfTU&si=4YFwPQTjTlTsxOMV"
python corrigir_artistas.py