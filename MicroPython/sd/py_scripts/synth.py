"""
Memory-Efficient Synthesizer for PicoCalc
Features:
- Basic waveform generation
- Simple envelope control
- Only essential features to fit in memory
"""
import picocalc
import math
import utime
import gc
from machine import Pin, PWM

# Free up memory before starting
gc.collect()

# Audio pins for PicoCalc
AUDIO_LEFT = 28  # PWM_L
AUDIO_RIGHT = 27  # PWM_R

# Define note frequencies (middle octave - 4)
BASE_NOTES = {
    'C': 262,
    'C#': 277,
    'D': 294,
    'D#': 311,
    'E': 330,
    'F': 349,
    'F#': 370,
    'G': 392,
    'G#': 415,
    'A': 440,
    'A#': 466,
    'B': 494
}

# Arrow key escape sequences for PicoCalc
KEY_UP = b'\x1b[A'      # Up arrow
KEY_DOWN = b'\x1b[B'    # Down arrow
KEY_LEFT = b'\x1b[D'    # Left arrow
KEY_RIGHT = b'\x1b[C'   # Right arrow
KEY_ESC = b'\x1b\x1b'   # Escape key (double ESC sequence)

class CompactSynth:
    def __init__(self):
        # Display setup
        self.display = picocalc.display
        self.width, self.height = self.display.width, self.display.height
        
        # Initialize audio PWM
        self.audio_left = PWM(Pin(AUDIO_LEFT))
        self.audio_right = PWM(Pin(AUDIO_RIGHT))
        
        # Synth settings
        self.waveform = 0  # 0=square, 1=pulse, 2=saw, 3=triangle, 4=sine
        self.waveform_names = ["Square", "Pulse", "Saw", "Triangle", "Sine"]
        
        # Note and octave
        self.note_names = list(BASE_NOTES.keys())
        self.current_note_index = self.note_names.index('A')
        self.octave = 4
        
        # Current frequency
        self.frequency = BASE_NOTES[self.note_names[self.current_note_index]]
        
        # State
        self.is_playing = False
        self.use_detune = True
        self.detune_amount = 3
        self.pulse_width = 0.5
        self.volume = 1.0
        
        # Input buffer
        self.key_buffer = bytearray(10)
        
        # Initialize display
        self.display.fill(0)
        self.update_display()
        
        print("Synth initialized on pins", AUDIO_LEFT, "and", AUDIO_RIGHT)
    
    def update_frequency(self):
        """Calculate frequency based on note and octave"""
        base_freq = BASE_NOTES[self.note_names[self.current_note_index]]
        octave_diff = self.octave - 4
        self.frequency = base_freq * (2 ** octave_diff)
    
    def update_display(self):
        """Update display with current synth state"""
        # Clear display
        self.display.fill(0)
        
        # Title
        self.display.text("PicoCalc Synth", 10, 10, 1)
        
        # Current note and frequency
        note_name = self.note_names[self.current_note_index]
        self.display.text(f"Note: {note_name}{self.octave}", 10, 30, 1)
        self.display.text(f"Freq: {int(self.frequency)} Hz", 10, 45, 1)
        
        # Waveform
        wf_name = self.waveform_names[self.waveform]
        self.display.text(f"Wave: {wf_name}", 10, 60, 1)
        
        # Status
        status = "PLAYING" if self.is_playing else "STOPPED"
        self.display.text(f"Status: {status}", 10, 75, 1)
        
        # Effects
        if self.use_detune:
            self.display.text("Detune: ON", 10, 90, 1)
        
        # Draw waveform visualization
        self.draw_waveform()
        
        # Controls
        self.display.text("Controls:", 10, 180, 1)
        self.display.text("<>: Change Note", 20, 195, 1)
        self.display.text("^v: Octave Up/Down", 20, 210, 1)
        self.display.text("W: Change Waveform", 20, 225, 1)
        self.display.text("P: Play/Stop", 20, 240, 1)
        self.display.text("D: Toggle Detune", 20, 255, 1)
        self.display.text("ESC: Exit", 20, 270, 1)
        
        # Show the display
        self.display.show()
    
    def draw_waveform(self):
        """Draw current waveform visualization"""
        x, y = 10, 120
        width, height = 300, 40
        
        # Draw bounding box
        self.display.rect(x, y, width, height, 1)
        
        # Draw based on waveform type
        middle_y = y + height // 2
        
        if self.waveform == 0:  # Square
            # Draw square wave
            segment = 30
            for i in range(0, width, segment):
                half = segment // 2
                # High part
                self.display.hline(x + i, y + 10, half, 1)
                # Vertical
                self.display.vline(x + i + half, y + 10, height - 20, 1)
                # Low part
                self.display.hline(x + i + half, middle_y + 10, half, 1)
                
        elif self.waveform == 1:  # Pulse
            # Draw pulse wave
            segment = 30
            pulse = int(segment * self.pulse_width)
            for i in range(0, width, segment):
                # High part
                self.display.hline(x + i, y + 10, pulse, 1)
                # Vertical
                self.display.vline(x + i + pulse, y + 10, height - 20, 1)
                # Low part
                self.display.hline(x + i + pulse, middle_y + 10, segment - pulse, 1)
                
        elif self.waveform == 2:  # Sawtooth
            # Draw sawtooth wave
            segment = 30
            for i in range(0, width, segment):
                # Rising line
                self.display.line(x + i, middle_y + 10, x + i + segment, y + 10, 1)
                # Vertical reset
                self.display.line(x + i + segment, y + 10, x + i + segment, middle_y + 10, 1)
                
        elif self.waveform == 3:  # Triangle
            # Draw triangle wave
            segment = 30
            half = segment // 2
            for i in range(0, width, segment):
                # Rising edge
                self.display.line(x + i, middle_y + 10, x + i + half, y + 10, 1)
                # Falling edge
                self.display.line(x + i + half, y + 10, x + i + segment, middle_y + 10, 1)
                
        elif self.waveform == 4:  # Sine
            # Draw sine wave
            prev_x, prev_y = x, middle_y
            for i in range(width):
                # Calculate sine
                angle = (i / width) * 2 * math.pi * 2
                value = math.sin(angle)
                curr_y = int(middle_y + value * (height // 2 - 5))
                
                # Draw line segment
                if i > 0:
                    self.display.line(prev_x, prev_y, x + i, curr_y, 1)
                prev_x, prev_y = x + i, curr_y
    
    def get_duty_cycle(self):
        """Get PWM duty cycle for current waveform"""
        if self.waveform == 0:  # Square
            return 32768  # 50% duty
        elif self.waveform == 1:  # Pulse
            return int(65535 * self.pulse_width)
        elif self.waveform == 2:  # Sawtooth
            return 55000  # Approximation
        elif self.waveform == 3:  # Triangle
            return 32768  # 50% duty
        elif self.waveform == 4:  # Sine
            return 32768  # Will be modulated
        return 32768
    
    def play_note(self):
        """Play current note"""
        # Set frequencies
        self.audio_left.freq(int(self.frequency))
        
        # Apply detune to right channel if enabled
        right_freq = self.frequency
        if self.use_detune:
            right_freq += self.detune_amount
        self.audio_right.freq(int(right_freq))
        
        # Set duty cycle
        duty = self.get_duty_cycle()
        self.audio_left.duty_u16(duty)
        self.audio_right.duty_u16(duty)
        
        # Update state
        self.is_playing = True
        print(f"Playing {self.note_names[self.current_note_index]}{self.octave} ({int(self.frequency)} Hz)")
        self.update_display()
    
    def stop_note(self):
        """Stop playback"""
        self.audio_left.duty_u16(0)
        self.audio_right.duty_u16(0)
        self.is_playing = False
        print("Sound stopped")
        self.update_display()
    
    def toggle_note(self):
        """Toggle between play and stop"""
        if self.is_playing:
            self.stop_note()
        else:
            self.play_note()
    
    def next_note(self):
        """Change to next note"""
        self.current_note_index = (self.current_note_index + 1) % len(self.note_names)
        self.update_frequency()
        
        if self.is_playing:
            self.play_note()
        else:
            self.update_display()
    
    def prev_note(self):
        """Change to previous note"""
        self.current_note_index = (self.current_note_index - 1) % len(self.note_names)
        self.update_frequency()
        
        if self.is_playing:
            self.play_note()
        else:
            self.update_display()
    
    def octave_up(self):
        """Increase octave"""
        if self.octave < 7:
            self.octave += 1
            self.update_frequency()
            
            if self.is_playing:
                self.play_note()
            else:
                self.update_display()
    
    def octave_down(self):
        """Decrease octave"""
        if self.octave > 1:
            self.octave -= 1
            self.update_frequency()
            
            if self.is_playing:
                self.play_note()
            else:
                self.update_display()
    
    def cycle_waveform(self):
        """Change to next waveform"""
        self.waveform = (self.waveform + 1) % len(self.waveform_names)
        
        if self.is_playing:
            self.play_note()
        else:
            self.update_display()
    
    def toggle_detune(self):
        """Toggle stereo detune effect"""
        self.use_detune = not self.use_detune
        
        if self.is_playing:
            if self.use_detune:
                self.audio_right.freq(int(self.frequency + self.detune_amount))
            else:
                self.audio_right.freq(int(self.frequency))
        
        self.update_display()
    
    def handle_input(self):
        """Process keyboard input"""
        if not picocalc.terminal:
            return False
        
        # Read keys from terminal
        count = picocalc.terminal.readinto(self.key_buffer)
        if not count:
            return False
        
        # Get the key data
        key_data = bytes(self.key_buffer[:count])
        
        # Check for ESC key (exit)
        if key_data == KEY_ESC:
            self.exit_synth()
            return "EXIT"
        
        # Handle arrow keys
        if key_data == KEY_LEFT:
            self.prev_note()
            return True
            
        elif key_data == KEY_RIGHT:
            self.next_note()
            return True
            
        elif key_data == KEY_UP:
            self.octave_up()
            return True
            
        elif key_data == KEY_DOWN:
            self.octave_down()
            return True
        
        # Handle other keys (single character)
        if count == 1:
            key = self.key_buffer[0]
            
            # Play/Stop with P key
            if key == ord('p') or key == ord('P'):
                self.toggle_note()
                return True
                
            # Toggle detune with D key
            if key == ord('d') or key == ord('D'):
                self.toggle_detune()
                return True
                
            # Change waveform with W key
            if key == ord('w') or key == ord('W'):
                self.cycle_waveform()
                return True
                
            # Play notes with number keys 1-7
            if key >= ord('1') and key <= ord('7'):
                note_idx = key - ord('1')
                if note_idx < len(self.note_names):
                    self.current_note_index = note_idx
                    self.update_frequency()
                    if self.is_playing:
                        self.play_note()
                    else:
                        self.update_display()
                    return True
        
        return True
    
    def exit_synth(self):
        """Clean up before exiting"""
        # Stop any playing sound
        if self.is_playing:
            self.stop_note()
            
        # Clear display
        self.display.fill(0)
        self.display.text("Exiting synthesizer...", 10, 10, 1)
        self.display.show()
        
        print("Exiting synthesizer...")
        utime.sleep(1)
    
    def run(self):
        """Main synthesizer loop"""
        print("Starting synthesizer...")
        print("Press ESC to exit")
        
        # Play a test note
        print("Playing test note (A4)...")
        self.play_note()
        utime.sleep(1)
        self.stop_note()
        
        try:
            while True:
                # Check for keyboard input
                result = self.handle_input()
                if result == "EXIT":
                    break
                
                # Only for sine waveform: update duty cycle to simulate sine
                if self.is_playing and self.waveform == 4:
                    # Simple sine wave simulation by modulating PWM duty
                    t = utime.ticks_ms() / 500.0  # Time factor
                    sine_val = math.sin(2 * math.pi * t * 2)
                    
                    # Map -1..1 to 0..65535 for duty cycle
                    duty = int(32768 + sine_val * 32767 * self.volume)
                    self.audio_left.duty_u16(duty)
                    
                    # Also update right channel with slight phase offset
                    sine_val_r = math.sin(2 * math.pi * t * 2 + 0.2)
                    duty_r = int(32768 + sine_val_r * 32767 * self.volume)
                    self.audio_right.duty_u16(duty_r)
                
                # Short delay to prevent tight loop
                utime.sleep_ms(10)
                
        except KeyboardInterrupt:
            self.stop_note()
            print("Synthesizer stopped")
        
        # Final cleanup
        self.stop_note()
        return

def main():
    # Force garbage collection before starting
    gc.collect()
    
    try:
        # Print available memory
        free = gc.mem_free()
        print(f"Free memory: {free} bytes")
        
        # Create and run synth
        synth = CompactSynth()
        synth.run()
        print("Synthesizer exited normally")
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.print_exception(e)

# For direct execution
if __name__ == "__main__":
    main()