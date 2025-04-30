# PicoCalc audio test script
from machine import Pin, PWM
import time

# Audio pins for PicoCalc
AUDIO_LEFT = 28
AUDIO_RIGHT = 27

# Initialize PWM for audio
audio_left = PWM(Pin(AUDIO_LEFT))
audio_right = PWM(Pin(AUDIO_RIGHT))

# Set frequency to audible range
audio_left.freq(440)  # 440 Hz = A4 note
audio_right.freq(440)

print("Testing audio output...")
print("You should hear a 440 Hz tone (A4 note)")

# Turn on sound at 50% volume
audio_left.duty_u16(32768)  # 50% duty cycle
audio_right.duty_u16(32768)

# Play for 3 seconds
print("Playing tone for 3 seconds...")
time.sleep(3)

# Sweep frequency to test range
print("Now sweeping frequency...")
for freq in range(220, 880, 10):
    audio_left.freq(freq)
    audio_right.freq(freq)
    time.sleep(0.05)

# Turn off sound
audio_left.duty_u16(0)
audio_right.duty_u16(0)

print("Audio test complete")