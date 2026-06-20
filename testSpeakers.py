import vlc
import time
import requests

original_url = "https://radio.garden/api/ara/content/listen/z2Qm6PAt/channel.mp3"

# Resolve the redirect to get the actual stream URL
resp = requests.head(original_url, allow_redirects=True, timeout=10)
url = resp.url
print(f"Resolved stream URL: {url}")

player = vlc.MediaPlayer(url)
player.play()

print("Streaming audio... Press Ctrl+C to stop.")
try:
    while True:
        time.sleep(1)
        state = player.get_state()
        if state in [vlc.State.Ended, vlc.State.Error]:
            break
except KeyboardInterrupt:
    print("\nStopping audio...")
    player.stop()
