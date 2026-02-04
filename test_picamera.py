from picamera2 import Picamera2
from PIL import Image

picam = Picamera2()
picam.configure(picam.create_still_configuration())
picam.start()

frame = picam.capture_array()
picam.stop()

Image.fromarray(frame).save("ok.png")
print("Camera OK")
