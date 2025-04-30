import picocalc
import math
import utime
import sys
from machine import Pin, PWM

# Audio pins for PicoCalc
AUDIO_LEFT = 28
AUDIO_RIGHT = 27

# Base frequencies for different notes (middle octave - 4)
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

# Special key codes
KEY_HOME = b'\x1b[H'    # Home key
KEY_END = b'\x1b[F'     # End key
KEY_DELETE = b'\x1b[3~' # Delete key
KEY_ESC = b'\x1b\x1b'   # Escape key (double ESC sequence)

class Synthesizer:
    def __init__(self):
        # Display setup
        self.display = picocalc.display
        self.width, self.height = self.display.width, self.display.height
        
        # Initialize audio PWM
        self.audio_left = PWM(Pin(AUDIO_LEFT))
        self.audio_right = PWM(Pin(AUDIO_RIGHT))
        
        # Oscillator settings
        self.oscillator_type = 0  # 0=square, 1=pulse, 2=sawtooth, 3=triangle, 4=sine
        self.oscillator_names = ["Square", "Pulse", "Sawtooth", "Triangle", "Sine"]
        
        # For sine wave simulation using PWM
        self.sine_phase = 0.0
        self.sine_update_timer = 0
        
        # Note and octave settings
        self.note_names = list(BASE_NOTES.keys())
        self.current_note_index = self.note_names.index('A')  # Start with A
        self.octave = 4  # Middle octave
        self.min_octave = 2
        self.max_octave = 6
        
        # Calculate current frequency
        self.update_frequency()
        
        # Synth state
        self.volume = 1.0     # Full volume
        self.playing = False
        self.detune_enabled = True
        self.detune_amount = 3  # Hz difference between channels
        self.pulse_width = 0.5  # For pulse oscillator (0.1 to 0.9)
        
        # Timing and animation variables
        self.phase_offset = 0.0
        self.key_buffer = bytearray(10)  # Buffer for key input
        
        # Initialize display
        self.display.fill(0)
        self.update_display()
        
        print("Audio initialized on pins", AUDIO_LEFT, "and", AUDIO_RIGHT)
    
    def update_frequency(self):
        """Calculate the current frequency based on note and octave"""
        base_freq = BASE_NOTES[self.note_names[self.current_note_index]]
        
        # Adjust for octave (each octave is 2x frequency)
        octave_diff = self.octave - 4  # Relative to middle octave
        self.frequency = base_freq * (2 ** octave_diff)
    
    def update_display(self):
        """Update the entire display with current synth state"""
        # Clear display
        self.display.fill(0)
        
        # Title and info
        self.display.text("PicoCalc Synthesizer", 10, 10, 1)
        
        # Show current note, octave and frequency
        current_note = self.note_names[self.current_note_index]
        self.display.text(f"Note: {current_note}{self.octave}", 10, 30, 1)
        self.display.text(f"Freq: {int(self.frequency)} Hz", 10, 45, 1)
        
        # Show oscillator type
        osc_name = self.oscillator_names[self.oscillator_type]
        self.display.text(f"Wave: {osc_name}", 10, 60, 1)
        
        # Show synth status
        status = "PLAYING" if self.playing else "STOPPED"
        self.display.text(f"Status: {status}", 10, 75, 1)
        
        # Show effects status
        effects = []
        if self.detune_enabled:
            effects.append("Stereo Detune")
        
        effects_text = ", ".join(effects) if effects else "None"
        self.display.text(f"Effects: {effects_text}", 10, 90, 1)
        
        # Draw controls
        self.display.text("Controls:", 10, 115, 1)
        self.display.text("←/→: Change Note", 20, 130, 1)
        self.display.text("↑/↓: Octave Up/Down", 20, 145, 1)
        self.display.text("O: Change Oscillator", 20, 160, 1)
        self.display.text("P: Play/Stop  D: Detune", 20, 175, 1)
        self.display.text("ESC: Exit", 20, 190, 1)
        
        # Draw waveform
        self.draw_waveform()
        
        # Show the updated display
        self.display.show()
    
    def draw_waveform(self):
        """Draw visual representation of the current oscillator type"""
        # Define waveform area
        wave_y = 210
        wave_height = 25
        
        # Draw baseline
        self.display.hline(0, wave_y, self.width, 1)
        
        # Draw waveform based on current oscillator type
        prev_x, prev_y = 0, wave_y
        
        if self.oscillator_type == 0:  # Square
            # Draw square wave
            segment_width = 20  # Width of one cycle
            for x in range(0, self.width, segment_width):
                # Draw high part
                y_high = wave_y - wave_height
                self.display.hline(x, y_high, segment_width // 2, 1)
                self.display.vline(x, y_high, wave_height, 1)
                
                # Draw low part
                self.display.hline(x + segment_width // 2, wave_y, segment_width // 2, 1)
                self.display.vline(x + segment_width // 2, y_high, wave_height, 1)
                
        elif self.oscillator_type == 1:  # Pulse
            # Draw pulse wave (asymmetric square)
            segment_width = 20  # Width of one cycle
            pulse_point = int(segment_width * self.pulse_width)
            
            for x in range(0, self.width, segment_width):
                # Draw high part
                y_high = wave_y - wave_height
                self.display.hline(x, y_high, pulse_point, 1)
                self.display.vline(x, y_high, wave_height, 1)
                
                # Draw low part
                self.display.hline(x + pulse_point, wave_y, segment_width - pulse_point, 1)
                self.display.vline(x + pulse_point, y_high, wave_height, 1)
                
        elif self.oscillator_type == 2:  # Sawtooth
            # Draw sawtooth wave
            segment_width = 20  # Width of one cycle
            for x in range(0, self.width, segment_width):
                # Draw rising edge
                self.display.line(x, wave_y, x + segment_width, wave_y - wave_height, 1)
                # Draw vertical reset
                self.display.line(x + segment_width, wave_y - wave_height, x + segment_width, wave_y, 1)
                
        elif self.oscillator_type == 3:  # Triangle
            # Draw triangle wave
            segment_width = 20  # Width of one cycle
            half_segment = segment_width // 2
            for x in range(0, self.width, segment_width):
                # Draw rising edge
                self.display.line(x, wave_y, x + half_segment, wave_y - wave_height, 1)
                # Draw falling edge
                self.display.line(x + half_segment, wave_y - wave_height, x + segment_width, wave_y, 1)
                
        elif self.oscillator_type == 4:  # Sine
            # Draw sine wave
            segment_width = 20  # Width of one cycle
            prev_x, prev_y = 0, wave_y
            
            for x in range(0, self.width, 2):
                # Calculate sine value
                phase = (x / segment_width) * 2 * math.pi
                sine_val = math.sin(phase)
                
                # Convert to y coordinate
                y = wave_y - int(sine_val * wave_height)
                
                # Draw line segment
                if x > 0:
                    self.display.line(prev_x, prev_y, x, y, 1)
                
                prev_x, prev_y = x, y
    
    def get_duty_cycle_for_oscillator(self):
        """Return the appropriate duty cycle for the current oscillator"""
        if self.oscillator_type == 0:  # Square
            return 32768  # 50% duty
        elif self.oscillator_type == 1:  # Pulse
            # Map pulse width (0.1-0.9) to duty cycle
            return int(65535 * self.pulse_width)
        elif self.oscillator_type == 2:  # Sawtooth - approximate with high duty cycle
            return 55000  # Skewed toward high
        elif self.oscillator_type == 3:  # Triangle - approximate with mid duty cycle
            return 32768  # 50% duty again
        elif self.oscillator_type == 4:  # Sine - we'll simulate with dynamic duty cycle
            return 32768  # Start at 50% and will modulate
        return 32768  # Default to 50%
    
    def update_sine_wave(self):
        """Update the duty cycle to simulate a sine wave"""
        if self.oscillator_type == 4 and self.playing:
            # Generate a sine wave by modulating the PWM duty cycle
            self.sine_phase += 0.1
            if self.sine_phase > 2 * math.pi:
                self.sine_phase -= 2 * math.pi
            
            # Calculate new duty cycle based on sine wave
            # Map sine (-1 to 1) to duty cycle (0 to 65535)
            sine_val = math.sin(self.sine_phase)
            duty = int(32768 + sine_val * 32767 * self.volume)
            
            # Apply to both channels
            self.audio_left.duty_u16(duty)
            self.audio_right.duty_u16(duty)
    
    def play_note(self):
        """Start playing the current note"""
        # Set base frequency for both channels
        self.audio_left.freq(int(self.frequency))
        
        # Apply detune to right channel if enabled
        right_freq = self.frequency
        if self.detune_enabled:
            right_freq += self.detune_amount
        self.audio_right.freq(int(right_freq))
        
        # Reset sine phase for sine oscillator
        self.sine_phase = 0.0
        
        # Set duty cycle based on oscillator type
        duty = self.get_duty_cycle_for_oscillator()
        self.audio_left.duty_u16(duty)
        self.audio_right.duty_u16(duty)
        
        # Update state
        self.playing = True
        print(f"Playing {self.note_names[self.current_note_index]}{self.octave} ({int(self.frequency)} Hz) with {self.oscillator_names[self.oscillator_type]} wave")
        self.update_display()
    
    def stop_note(self):
        """Stop current playback"""
        self.audio_left.duty_u16(0)
        self.audio_right.duty_u16(0)
        self.playing = False
        print("Sound stopped")
        self.update_display()
    
    def toggle_note(self):
        """Toggle between play and stop"""
        if self.playing:
            self.stop_note()
        else:
            self.play_note()
    
    def next_note(self):
        """Change to next note in scale"""
        # Move to next note in list
        self.current_note_index = (self.current_note_index + 1) % len(self.note_names)
        
        # Update frequency
        self.update_frequency()
        
        # Update display and audio if playing
        print(f"Changed to note: {self.note_names[self.current_note_index]}{self.octave} ({int(self.frequency)} Hz)")
        if self.playing:
            self.play_note()
        else:
            self.update_display()
    
    def prev_note(self):
        """Change to previous note in scale"""
        # Move to previous note in list
        self.current_note_index = (self.current_note_index - 1) % len(self.note_names)
        
        # Update frequency
        self.update_frequency()
        
        # Update display and audio if playing
        print(f"Changed to note: {self.note_names[self.current_note_index]}{self.octave} ({int(self.frequency)} Hz)")
        if self.playing:
            self.play_note()
        else:
            self.update_display()
    
    def octave_up(self):
        """Increase octave by one"""
        if self.octave < self.max_octave:
            self.octave += 1
            self.update_frequency()
            
            print(f"Octave up: {self.octave}")
            if self.playing:
                self.play_note()
            else:
                self.update_display()
    
    def octave_down(self):
        """Decrease octave by one"""
        if self.octave > self.min_octave:
            self.octave -= 1
            self.update_frequency()
            
            print(f"Octave down: {self.octave}")
            if self.playing:
                self.play_note()
            else:
                self.update_display()
    
    def cycle_oscillator(self):
        """Cycle to the next oscillator type"""
        self.oscillator_type = (self.oscillator_type + 1) % len(self.oscillator_names)
        
        print(f"Changed oscillator to: {self.oscillator_names[self.oscillator_type]}")
        
        # Update audio if playing
        if self.playing:
            self.play_note()
        else:
            self.update_display()
    
    def toggle_detune(self):
        """Toggle stereo detune effect"""
        self.detune_enabled = not self.detune_enabled
        print(f"Detune effect {'enabled' if self.detune_enabled else 'disabled'}")
        
        # Update audio if playing
        if self.playing:
            # Reapply detune or set both channels to same frequency
            if self.detune_enabled:
                self.audio_right.freq(int(self.frequency + self.detune_amount))
            else:
                self.audio_right.freq(int(self.frequency))
        
        self.update_display()
    
    def handle_arrow_key(self, key_data):
        """Handle arrow key input"""
        if key_data == KEY_UP:
            self.octave_up()
            return True
        elif key_data == KEY_DOWN:
            self.octave_down()
            return True
        elif key_data == KEY_LEFT:
            self.prev_note()
            return True
        elif key_data == KEY_RIGHT:
            self.next_note()
            return True
        return False
    
    def handle_input(self):
        """Check for and process keyboard input"""
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
            # Clear display
            self.display.fill(0)
            self.display.text("Exiting synthesizer...", 10, 10, 1)
            self.display.show()
            
            # Stop any playing sound
            if self.playing:
                self.stop_note()
                
            print("Exiting synthesizer...")
            utime.sleep(1)  # Brief pause to show exit message
            
            # Return False to indicate exit
            return "EXIT"
        
        # Check for arrow keys
        if self.handle_arrow_key(key_data):
            return True
        
        # Check for other keys - single character keys
        if count == 1:
            key = self.key_buffer[0]
            
            # Play/stop with P key
            if key == ord('p') or key == ord('P'):
                self.toggle_note()
                return True
                
            # Toggle detune with D key
            if key == ord('d') or key == ord('D'):
                self.toggle_detune()
                return True
                
            # Cycle oscillator with O key
            if key == ord('o') or key == ord('O'):
                self.cycle_oscillator()
                return True
                
            # Play notes with number keys 1-7 (C through B)
            if key >= ord('1') and key <= ord('7'):
                note_idx = key - ord('1')
                if note_idx < len(self.note_names):
                    self.current_note_index = note_idx
                    self.update_frequency()
                    if self.playing:
                        self.play_note()
                    else:
                        self.update_display()
                    return True
                    
            # Octave selection with shift+number keys
            if key >= ord('!') and key <= ord('5'):  # Shift+1 through Shift+5
                new_octave = key - ord('!') + 2  # Map to octaves 2-6
                if self.min_octave <= new_octave <= self.max_octave:
                    self.octave = new_octave
                    self.update_frequency()
                    if self.playing:
                        self.play_note()
                    else:
                        self.update_display()
                    return True
        
        return True
    
    def run(self):
        """Main synthesizer loop"""
        print("Starting synthesizer...")
        print("Press ESC to exit")
        
        # Play a test note
        print("Playing test note (A4)...")
        self.play_note()
        utime.sleep(1)
        self.stop_note()
        
        last_time = utime.ticks_ms()
        
        try:
            while True:
                # Check for keyboard input
                result = self.handle_input()
                if result == "EXIT":
                    break
                
                # Calculate elapsed time
                current_time = utime.ticks_ms()
                elapsed = utime.ticks_diff(current_time, last_time)
                last_time = current_time
                
                # Update sine wave if needed
                if self.oscillator_type == 4 and self.playing:
                    self.sine_update_timer += elapsed
                    if self.sine_update_timer >= 5:  # Update every 5ms
                        self.update_sine_wave()
                        self.sine_update_timer = 0
                
                # Update the display occasionally to reduce flicker
                self.phase_offset += 0.01
                if int(self.phase_offset * 100) % 50 == 0:
                    self.update_display()
                
                # Short delay to prevent tight loop
                utime.sleep_ms(10)
                
        except KeyboardInterrupt:
            self.stop_note()
            print("Synthesizer stopped")
        
        # Final cleanup
        self.stop_note()
        return

def main():
    try:
        synth = Synthesizer()
        synth.run()
        print("Synthesizer exited normally")
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.print_exception(e)

# Direct execution for py_run.py compatibility
main()
