import asyncio
import httpx
from shazamio import Shazam

# Your Radio Garden API link that redirects to the live audio stream
RADIO_STREAM_URL = "http://radio.garden/api/ara/content/listen/1vlrqH6v/channel.mp3"


# 128kbps stream = ~16,000 bytes per second. 10 seconds ≈ 160,000 bytes.
CHUNK_SIZE = 160000 

async def identify_live_radio():
    shazam = Shazam()
    
    print("Connecting to live radio stream...")
    # CRITICAL FIX: Enable follow_redirects=True here
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async with client.stream("GET", RADIO_STREAM_URL) as response:
            print("Listening to stream (capturing 10 seconds of audio)...")
            
            audio_bytes = b""
            async for chunk in response.aiter_bytes():
                audio_bytes += chunk
                print(f"Captured {len(audio_bytes)} / {CHUNK_SIZE} bytes...", end="\r")
                
                if len(audio_bytes) >= CHUNK_SIZE:
                    audio_bytes = audio_bytes[:CHUNK_SIZE]
                    break
            
            print(f"\nCaptured complete chunk ({len(audio_bytes)} bytes).")
            
            if len(audio_bytes) < 50000:
                print("❌ Error: Stream closed early. Did not collect enough data.")
                return

            print("Analyzing audio bytes with Shazam...")
            try:
                result = await shazam.recognize(audio_bytes)
                if result and 'track' in result:
                    track_title = result['track']['title']
                    artist = result['track']['subtitle']
                    print(f"✅ Success! Currently Playing: {track_title} by {artist}")
                else:
                    print("❌ Match not found. The song might not be in Shazam's database.")
            except Exception as e:
                print(f"❌ Recognition Error: {e}")

# Run the asynchronous loop
asyncio.run(identify_live_radio())

