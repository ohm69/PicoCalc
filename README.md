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

1. **Download the UF2**  
   Grab the latest `MicroPython-PicoCalc-Pico2W.uf2` from the `firmware/` folder and copy it onto your PicoCalc via USB.

2. **Copy Modules & Scripts**  
   Format an SD-card to FAT32 and create a folder named `/sd`.  
   - Copy everything in `modules/` into the root of the MicroPython filesystem (so that `picocalcdisplay/` and `pico_keyboard.py` end up in `/modules/`).  
   - Copy the entire `sd/py_scripts/` folder to the SD card’s `/sd/py_scripts/`.

3. **Boot & Run**  
   - Power up PicoCalc (Pico 2W).  
   - The `boot.py` menu will appear—use the keyboard to select and run any script.

---

## 🚀 Usage

- **Menu Navigation**  
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

- **MicroPython** for RP2040 (tested with **Raspberry Pi Pico 2W**, MicroPython v1.19.1)  
- **Clockwork Pi PicoCalc** hardware (320×320 LCD, membrane keyboard, SD-card slot)  

---

## 📄 License

This project is released under the [MIT License](LICENSE). Feel free to use, modify, and distribute!

---

## ✉️ Contact

For questions or feedback, open an [issue](https://github.com/LofiFren/PicoCalc/issues) find me on: 
IG: [https://www.instagram.com/lofifren/]
YT: [https://www.youtube.com/@lofifren]

> **Tip:** After flashing the UF2, make sure the SD-card is properly seated and formatted FAT32. Enjoy tinkering!

