# merTears

<p align="center">
    <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
    <img src="https://img.shields.io/badge/Discord.py-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord.py" />
    <img src="https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp" />
    <img src="https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg" />
    <img src="https://img.shields.io/badge/PyNaCl_(Opus)-4B8BBE?style=for-the-badge&logo=pypi&logoColor=white" alt="PyNaCl" />
    <img src="https://img.shields.io/badge/AsyncIO-00599C?style=for-the-badge&logo=cplusplus&logoColor=white" alt="AsyncIO" />
    <img src="https://img.shields.io/badge/Dotenv-ECD53F?style=for-the-badge&logo=dotenv&logoColor=black" alt="Dotenv" />
    <img src="https://img.shields.io/badge/Spotify-1ED760?style=for-the-badge&logo=spotify&logoColor=white" alt="Spotify" />
</p>

Local Discord music bot powered by yt-dlp and FFmpeg

# Requirements
- Python 3.10 or +
- FFmpeg
- * Windows:
     ```powershell
     winget install Gyan.FFmpeg
     ```

## Clone
```
git clone https://github.com/zCyiBei/merTears.git
cd merTears
```
## Env
```
python -m venv venv
```
*  Windows:
```
venv\Scripts\activate
```
* Linux/macOS:
```
source venv/bin/activate
```

## Dependencies
```
pip install -r requirements.txt
```
- Create a .env file and add your tokens

## Start
```
python main.py
```

## Commands
- !join
- !play
- !pause
- !resume
- !loop
- !queue
- !stop
- !leave
