import subprocess

def display_tty_image(image_path):
    """
    Displays an image directly onto the Raspberry Pi TFT framebuffer indefinitely.
    """
    try:
        subprocess.run([
            "fbi",
            "-d", "/dev/fb1",
            "--noverbose",
            "-a",
            image_path
        ])
    except KeyboardInterrupt:
        print("Image display stopped")
    except Exception as e:
        print(f"Error rendering image: {e}")

if __name__ == "__main__":
    IMAGE = "/home/shmank/flaskServer/uploads/daxter-jak-3.gif"
    display_tty_image(IMAGE)
