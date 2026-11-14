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
  screen edges. A **hard landing** hurts it.
- **Hit it** with a quick left click: it flinches and turns to face you. On
  the sixth hit it **dies** and disappears.
- **Heals** over time: after a few seconds without being hit, it recovers
  one hit at a time.
- **Runs away** from the cursor when it has only two hits left (dashing if
  the cursor is very close and hopping around to dodge your clicks), until it
  has healed a bit.
- **Celebrates** with a couple of hops when one of its swings breaks the
  dummy.
- **Shows its health**: put the cursor over Parton and a row of hearts
  appears above its head. It has three, and each heart is two hits: the first
  turns it into a half heart, the second empties it.

### The training dummy

The dummy (`dummy.py`) comes up together with Parton, in the same program:

- It starts in the bottom-left corner of the screen, on the taskbar.
- **Hit it** with a quick left click: the cursor turns into a sword over it.
- **Pick it up and throw it** just like Parton, but it is **twice as heavy**:
  the same flick throws it half as fast, and it bounces less off the edges.
  Unlike Parton, landings don't hurt it.
- Put the cursor over it to see its health: seven hearts, two hits each.
- Your hits and Parton's add up, even while it is in the air: on the 14th it
  **breaks** and disappears, and **comes back** on its own 15 seconds later.

### Throwing them at each other

- Throw Parton hard at the dummy and the dummy takes a hit (Parton bounces
  off it).
- Throw the dummy hard at Parton, or drop it on him, and Parton takes a hit...
  unless he dodges: three times out of four he waits until the last moment
  and then **jumps over it** or **dashes out of the way**, whichever gets him
  clear. If it comes too close and too fast for either, he takes the hit.
- A dummy that hits Parton also **knocks him back**: he is pushed the way it
  was flying (or away from it, if it fell on him) with a little hop.
- A gentle toss doesn't hurt: from the side only the sideways speed counts,
  and falling on top of the other one, the whole speed. One hit per throw.

### The menu

Right click on Parton or on the dummy to open a small menu of pixel-art
buttons (or the plain Windows menu if the font is missing). Click an option
to pick it; click anywhere else or press Escape to close it:

- **Revive** a character that has died (the dummy without waiting).
- **Hide** or **show** each one, to have only one of them on the screen. A
  hidden dummy doesn't come back on its own.
- **Settings**, each one switched on or off with a click:
  - **Calm mode** (off by default): Parton ignores the cursor, so he no
    longer chases or attacks it. You can still hit him.
  - **Do not disturb** (on by default): both hide while a full-screen app is
    in front (a game, a video, a presentation) and come back when it closes.
  - **Training** (on by default): Parton goes and hits the dummy now and then.
- **Exit** closes the program.

The settings are saved in `%APPDATA%\Parton\settings.json`, so they are kept
the next time it runs.

If neither of them is left on the screen (both dead or hidden) and the dummy
isn't about to come back, there is nothing left to right-click, so the
program closes; run it again to bring both back. Only one copy of the program
runs at a time.

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
   Art** pack by Mattz Art from <https://xzany.itch.io/> and copy its
   `IDLE.png`, `HIT.png` and `BREAKING.png` into `assets/dummy/sprites/`.
3. *(Optional, for the sword cursor)* Download the free **Pixel Cursors &
   Icons** pack by Willosuna from <https://willosuna.itch.io/> and run
   `python make_cursor.py`. It looks for `pixel-cursors-icons-r4.zip` in your
   Downloads or `Pictures/Assets` folder (or pass its path as an argument) and
   creates `assets/cursor/sword.cur`.
4. *(Optional, for the pixel-art menu)* Copy the **Nanofon** pixel font to
   `assets/ui/Nanofon.ttf`. The menu's buttons and the hearts are drawn by
   the program itself, so nothing else is needed.
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
├── cursor/
│   └── sword.cur
└── ui/
    └── Nanofon.ttf
```

If any of Parton's sprites is missing, it shows a message listing the missing
files. Without the dummy's sprites, Parton runs alone; without the sword
cursor, the dummy shows a hand cursor. Without the font, the menu is the plain
Windows one (the hearts don't need anything).

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
| `HITS_TO_DIE`, `DEATH_LINGER` | Hits it takes to die (keep it even: two hits per heart), and how long it lies there before disappearing |
| `HEAL_DELAY`, `HEAL_INTERVAL` | How long without being hit before it heals, and how often it heals a hit |
| `FLEE_AT`, `FLEE_DASH_DISTANCE` | With how many hits left it runs away, and how close the cursor must be for it to dash |
| `FLEE_JUMP_HEIGHT`, `FLEE_JUMPS_PER_SECOND` | Height of its dodging hops while fleeing, and how often it hops (cursor far / close) |
| `CELEBRATE_HOPS`, `CELEBRATE_HOP_HEIGHT` | How many hops it does after breaking the dummy, and how high |
| `TRAIN_CHANCE`, `TRAIN_RANGE` | How often it goes to train on the dummy, and from how far |
| `TRAIN_SWINGS`, `TRAIN_PAUSE` | How many swings per training session, and the pause between them |
| `EVADE_CHANCE`, `EVADE_MARGIN` | How often it dodges a thrown dummy (the rest of the time it takes the hit), and how close to the last moment it waits before dodging |
| `EVADE_JUMP_HEIGHT`, `EVADE_DASH_DISTANCE` | How high it jumps and how far it dashes to dodge |
| `KNOCKBACK_FACTOR`, `KNOCKBACK_MAX`, `KNOCKBACK_LIFT` | How hard a hit from the dummy pushes Parton (share of its speed, cap) and how much it pops him up |
| `FULLSCREEN_CHECK_MS` | How often "do not disturb" looks for a full-screen app |

`physics.py` holds what Parton and the dummy share:

| Setting | What it changes |
|---|---|
| `GRAVITY` | How fast things fall |
| `THROW_FACTOR`, `THROW_MAX_SPEED` | How much of the mouse speed a throw keeps, and its cap |
| `THROW_FLICK_SPEED`, `THROW_FLICK_FACTOR` | From what mouse speed sharp flicks get stronger, and how much |
| `AIR_DRAG`, `WALL_BOUNCE` | How quickly a throw slows down, and how much it bounces off the edges |
| `IMPACT_SPEED`, `IMPACT_BOUNCE` | How fast a thrown body must hit the other one to hurt it, and how much it bounces off |
| `FALL_DAMAGE_SPEED` | How fast a landing must be to hurt Parton |
| `DRAG_THRESHOLD`, `AIR_DRAG_THRESHOLD`, `HOLD_SECONDS` | How far you must move (on the ground / in the air), or how long you must hold, for a click to become a grab |

The dummy has its own settings at the top of `dummy.py` (`SCALE`,
`HITS_TO_DIE`, `RESPAWN_SECONDS`, `WEIGHT`, animation speeds and its starting distance from the
screen edge).

`ui.py` draws the menu and the hearts: `UI_SCALE` sets their pixel size
(keep it the same as the characters' `SCALE`), `HEART` is the heart's drawing, `TEXT_SCALE` the pixel size of
the menu's text (half the characters', so the buttons stay small), `HEARTS_GAP` how far above the head
the hearts sit and `HEART_GAP` the space between hearts.

## Credits

- Parton art by [Jesshiyoo](https://jesshiyoo.itch.io/).
- Dummy art by [Mattz Art](https://xzany.itch.io/).
- Sword cursor art by [Willosuna](https://willosuna.itch.io/); the menu and
  hearts use the colors of their Fantasy UI Kit Lite.
- Nanofon pixel font.

## License

The code is released under the [MIT License](LICENSE). The license covers the
code only: the art belongs to its authors and is subject to their own
licenses, which do not allow redistributing it.
