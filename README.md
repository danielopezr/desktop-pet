# Parton Desktop Pet

A small desktop pet for Windows, written in Python with Tkinter. Parton is the
"Little Axion" character from the *Luneblade* pack by Jesshiyoo. It lives on
your taskbar, hunts your mouse cursor with its axe and trains on a dummy.

## What it does

- **Wanders** along the bottom of the screen, standing on the taskbar: it
  idles for a few seconds, then runs to a random spot.
- **Trains** on the training dummy: now and then, when the dummy is close
  enough, Parton walks up to it and hits it a few times.
- **Chases the cursor** when it sees it nearby (up to 450 px to either side
  and 250 px above the taskbar). The cursor always comes before the dummy.
- **Attacks** with one of its two axe swings, picked at random, once the
  cursor is within reach.
- **Jumps** at the cursor when it is close but higher than the axe can reach,
  drifting towards it in the air, and **swings in mid-air** if it gets close
  enough.
- **Dashes back** when the cursor is right on top of it, to get the axe's
  distance, and then attacks.
- **Pick it up** by holding the left mouse button on it, and release it
  anywhere: it falls back down to the taskbar. Let go while moving the mouse
  and it is **thrown** that way, as fast as you were moving, bouncing off the
  screen edges.
- **Hit it** with a quick left click: it flinches and turns to face you. On
  the ninth hit it **dies** and disappears.

### The training dummy

The dummy (`dummy.py`) comes up together with Parton, in the same program:

- It starts in the bottom-left corner of the screen, on the taskbar.
- **Hit it** with a quick left click: the cursor turns into a sword over it.
- **Pick it up and throw it** just like Parton, but it is **twice as heavy**:
  the same flick throws it half as fast, and it bounces less off the edges.
- Your hits and Parton's add up, even while it is in the air: on the 17th it
  **breaks** and disappears.

### The menu

Right click on Parton or on the dummy to open a small menu:

- **Revive** a character that has died.
- **Hide** or **show** each one, to have only one of them on the screen.
- **Exit** closes the program.

If neither of them is left on the screen (both dead or hidden), there is
nothing left to right-click, so the program closes; run it again to bring
both back. Only one copy of the program runs at a time.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer, with Tkinter (included in the python.org installer)
- [Pillow](https://pypi.org/project/pillow/): `pip install pillow`

## Sprites (not included)

The sprites are **not** in this repository: the packs' licenses do not allow
redistributing them. To get them:

1. Download the free **Luneblade – Little Axion** pack by Jesshiyoo from
   <https://jesshiyoo.itch.io/> and copy its PNG sprite sheets into
   `assets/parton/sprites/`.
2. *(Optional, for the dummy)* Download the free **Training Dummy 2D Pixel
   Art** pack and copy its `IDLE.png`, `HIT.png` and `BREAKING.png` into
   `assets/dummy/sprites/`.
3. *(Optional, for the sword cursor)* Download the free **Pixel Cursors &
   Icons** pack by Willosuna from <https://willosuna.itch.io/> and run
   `python make_cursor.py`. It looks for `pixel-cursors-icons-r4.zip` in your
   Downloads or `Pictures/Assets` folder (or pass its path as an argument) and
   creates `assets/cursor/sword.cur`.

```
assets/
├── parton/
│   └── sprites/
│       ├── Attack 1.png
│       ├── Attack 2.png
│       ├── Dash.png
│       ├── Death.png
│       ├── Fall.png
│       ├── Hurt.png
│       ├── Idle.png
│       ├── Jump.png
│       └── Run.png
├── dummy/
│   └── sprites/
│       ├── BREAKING.png
│       ├── HIT.png
│       └── IDLE.png
└── cursor/
    └── sword.cur
```

If any of Parton's sprites is missing, it shows a message listing the missing
files. Without the dummy's sprites, Parton runs alone; without the sword
cursor, the dummy shows a hand cursor.

## Running it

```
pythonw parton.py
```

It brings up Parton and the dummy. `pythonw` runs it without a console
window; `python parton.py` also works.

## Settings

The constants at the top of `parton.py` control its behavior:

| Setting | What it changes |
|---|---|
| `SCALE` | Size of the character on screen |
| `RUN_SPEED`, `CHASE_SPEED` | Speed when wandering and when chasing |
| `IDLE_SECONDS` | How long it idles before wandering |
| `VISION_RANGE`, `VISION_HEIGHT` | How far it can see the cursor |
| `ATTACK_REACH`, `ATTACK_HEIGHT`, `SLASH_CENTER` | How far and how high the axe slash reaches, and where it aims |
| `TOO_CLOSE`, `DASH_SPEED` | When it dashes back, and how fast |
| `JUMP_MAX_HEIGHT`, `JUMP_PAUSE` | Highest jump, and the rest between jumps |
| `AIR_ATTACK_FRAME_MS` | Speed of the mid-air swing |
| `HITS_TO_DIE`, `DEATH_LINGER` | Hits it takes to die, and how long it lies there before disappearing |
| `TRAIN_CHANCE`, `TRAIN_RANGE` | How often it goes to train on the dummy, and from how far |
| `TRAIN_SWINGS`, `TRAIN_PAUSE` | How many swings per training session, and the pause between them |

`physics.py` holds what Parton and the dummy share:

| Setting | What it changes |
|---|---|
| `GRAVITY` | How fast things fall |
| `THROW_FACTOR`, `THROW_MAX_SPEED` | How much of the mouse speed a throw keeps, and its cap |
| `THROW_FLICK_SPEED`, `THROW_FLICK_FACTOR` | From what mouse speed sharp flicks get stronger, and how much |
| `AIR_DRAG`, `WALL_BOUNCE` | How quickly a throw slows down, and how much it bounces off the edges |
| `DRAG_THRESHOLD`, `AIR_DRAG_THRESHOLD`, `HOLD_SECONDS` | How far you must move (on the ground / in the air), or how long you must hold, for a click to become a grab |

The dummy has its own settings at the top of `dummy.py` (`SCALE`,
`HITS_TO_DIE`, `WEIGHT`, animation speeds and its starting distance from the
screen edge).

## Credits

- Parton art by [Jesshiyoo](https://jesshiyoo.itch.io/).
- Training dummy from the *Training Dummy 2D Pixel Art* pack.
- Sword cursor from *Pixel Cursors & Icons* by
  [Willosuna](https://willosuna.itch.io/).

## License

The code is released under the [MIT License](LICENSE). The license covers the
code only: the art belongs to its authors and is subject to their own
licenses, which do not allow redistributing it.
