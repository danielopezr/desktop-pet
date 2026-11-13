# Parton Desktop Pet

A small desktop pet for Windows, written in Python with Tkinter. Parton is the
"Little Axion" character from the *Luneblade* pack by Jesshiyoo. It lives on
your taskbar and hunts your mouse cursor with its axe.

## What it does

- **Wanders** along the bottom of the screen, standing on the taskbar: it
  idles for a few seconds, then runs to a random spot.
- **Chases the cursor** when it sees it nearby (up to 450 px to either side
  and 250 px above the taskbar).
- **Attacks** with one of its two axe swings, picked at random, once the
  cursor is within reach.
- **Just watches** when the cursor is close but higher than the axe can reach.
- **Dashes back** when the cursor is right on top of it, to get the axe's
  distance, and then attacks.
- Right click it to **exit**. Only one Parton runs at a time.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer, with Tkinter (included in the python.org installer)
- [Pillow](https://pypi.org/project/pillow/): `pip install pillow`

## Sprites (not included)

The sprites are **not** in this repository: the pack's license does not allow
redistributing them. To get them:

1. Download the free **Luneblade – Little Axion** pack by Jesshiyoo from
   <https://jesshiyoo.itch.io/>.
2. Copy its PNG sprite sheets into `assets/sprites/`:

```
assets/sprites/
├── Attack 1.png
├── Attack 2.png
├── Dash.png
├── Death.png
├── Fall.png
├── Hurt.png
├── Idle.png
├── Jump.png
└── Run.png
```

If any of them is missing, Parton shows a message listing the missing files.

## Running it

```
pythonw parton.py
```

`pythonw` runs it without a console window; `python parton.py` also works.

## Settings

The constants at the top of `parton.py` control its behavior:

| Setting | What it changes |
|---|---|
| `SCALE` | Size of the character on screen |
| `RUN_SPEED`, `CHASE_SPEED` | Speed when wandering and when chasing |
| `IDLE_SECONDS` | How long it idles before wandering |
| `VISION_RANGE`, `VISION_HEIGHT` | How far it can see the cursor |
| `ATTACK_REACH`, `ATTACK_HEIGHT` | How far the axe reaches |
| `TOO_CLOSE`, `DASH_SPEED` | When it dashes back, and how fast |

## Credits

Art by [Jesshiyoo](https://jesshiyoo.itch.io/).

## License

The code is released under the [MIT License](LICENSE). The license covers the
code only: the sprites belong to Jesshiyoo and are subject to their own
license, which does not allow redistributing them.
