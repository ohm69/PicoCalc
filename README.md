# PicoCalc MicroPython

A MicroPython firmware and script collection for the Clockwork Pi PicoCalc handheld device, powered by the **Raspberry Pi Pico 2W**. With this you can:

- Drive the 320×320 LCD display  
- Read the membrane keyboard  
- Browse a simple VF-terminal interface  
- Run SD-card scripts (synth, sample player, tests…)  
- Flash a ready-to-use UF2 image  

---

## 📂 Repository Structure

```
MicroPython/
├── boot.py
├── firmware/              ← prebuilt UF2 firmware images
├── modules/               ← custom MicroPython modules
│   ├── picocalcdisplay/   ← display driver & graphics primitives
│   ├── pico_keyboard.py   ← keyboard-scanning routines
│   ├── sdcard.py          ← SD-card mounting & I/O
│   └── vtterminal/        ← VT100‐style terminal emulator
├── sd/
│   └── py_scripts/        ← example scripts (synth, sim, test, …)
└── README.md              ← you are here
```

---

## ⚙️ Installation

### 1. Enter BOOTSEL mode & flash UF2

1. **Power off** your PicoCalc (unplug USB).  
2. **Press and hold** the **BOOTSEL** button on the Pico 2W module.  
3. **While holding**, connect the PicoCalc to your computer via USB.  
4. Release **BOOTSEL** once you see a new removable drive named `RPI-RP2`.  
5. On that drive, **drag and drop** `MicroPython-PicoCalc-Pico2W.uf2` from the `firmware/` folder.  
   - You can find the latest build at `MicroPython/firmware/MicroPython-PicoCalc-Pico2W.uf2`.  
6. The PicoCalc will reboot automatically and appear as a MicroPython REPL over USB.

> **Troubleshooting:**
> - If you don’t see `RPI-RP2`, ensure you’re holding the correct BOOTSEL button on the Pico 2W.
> - On Windows, install the [Raspberry Pi UF2 driver](https://raspberrypi.org/software) if needed.

### 2. Copy Modules & Scripts

1. Format an SD card to **FAT32** and insert it into the PicoCalc’s SD slot.  
2. On the Pico’s REPL (via Thonny or another serial terminal), create `/modules/` and `/sd/py_scripts/` folders if they don’t exist (On the PicoCalc):
   ```python
   import os
   os.mkdir('modules') if 'modules' not in os.listdir() else None
   os.mount(sdcard, '/sd')   # if not auto-mounted
   os.mkdir('/sd/py_scripts') if 'py_scripts' not in os.listdir('/sd') else None
   ```
3. Using Thonny’s **File → Upload** or your OS file explorer:
   - Copy everything in `modules/` (e.g. `picocalcdisplay/`, `pico_keyboard.py`) into the Pico’s `/modules/` directory.  
   - Copy `sd/py_scripts/` into the SD card’s `/sd/py_scripts/` folder.

### 3. Boot & Run

- **Power cycle** the PicoCalc (Turn off then remove micro usb then plug in and power on).  
- A menu from `boot.py` will appear on the 320×320 screen:  
  1. Simulator (`sim.py`)  
  2. Synth engine (`synth.py`)  
  3. Test routines (`test_script.py`)  
  R: Reload menu  F: Flush & reload modules  X: Exit to REPL

Press the corresponding key on the membrane keyboard to launch your script.

---

## 🚀 Usage

- **Menu Navigation**:  
  - `1`: Run the simulator (`py_scripts/sim.py`)  
  - `2`: Run the synth engine (`py_scripts/synth.py`)  
  - `3`: Run test routines (`py_scripts/test_script.py`)  
  - `R`: Reload the menu  
  - `F`: Flush & reload all modules  
  - `X`: Exit to the REPL  

- **Writing Your Own Scripts**  
  Drop additional `.py` files into `/sd/py_scripts/`. They’ll automatically show up in the menu.

---

## 🙏 Credits

This project builds on and incorporates code from the [PicoCalc-micropython-driver](https://github.com/zenodante/PicoCalc-micropython-driver/tree/main) by **zenodante**, notably:

- The **320×320 LCD display** driver  
- The **membrane keyboard** scanning logic  
- The **prebuilt UF2**–style MicroPython image  

---

## 🛠️ Dependencies

- **MicroPython** for RP2350 (tested with **Raspberry Pi Pico 2W**, MicroPython v1.19.1)  
- **Clockwork Pi PicoCalc** hardware (320×320 LCD, membrane keyboard, SD-card slot)  

---

## 📄 License

This project is released under the [MIT License](LICENSE). Feel free to use, modify, and distribute!

---

## ✉️ Contact

For questions or feedback, open an [issue](https://github.com/LofiFren/PicoCalc/issues) find me on: 
- IG: [https://www.instagram.com/lofifren/]
- YT: [https://www.youtube.com/@lofifren]

> **Tip:** After flashing the UF2, make sure the SD-card is properly seated and formatted FAT32. Enjoy tinkering!

