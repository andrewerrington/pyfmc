# pyfmc
Simple FMC/CDU for X-Plane using Raspberry Pi and pygame.

## Brief notes for installation:

1) Install pygame

For me, I had to install pip (for Python3) then use pip to install pygame
```
sudo apt-get install python3-pip

python3 -m pip install -U pygame --user

sudo apt-get install python3-sdl2
```

2) In raspi-config, I set my display DMT Mode 4 VGA 640x480 60Hz 4:3

```
sudo raspi-config

option 2
option D1
DMT Mode 4
Ok
Ok
Finish
```

You can also do this by editing `config.txt` directly.

3) Copy *pyfmc.py* and *DejaVuSans.ttf* to a directory

4) Change to the directory and run the program with
```
python3 pyfmc.py
```
