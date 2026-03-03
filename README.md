# MIDI to BDO Converter

Convert standard MIDI files to Black Desert Online's music composer format.
 ![Screenshot](screenshot.png)

## Features

- Multi-instrument support - automatically maps MIDI channels to BDO instruments
- GM percussion mapping (drum kit)
- Sustain pedal support (CC64)
- Tempo flattening for multi-tempo MIDIs
- Velocity control (stepped, rescale, or floor modes)
- Transpose
- Effector settings (reverb, delay, chorus)
- Owner ID loading from existing BDO files (for in-game edit access)

## Download

Go to the [Releases](https://github.com/Bishop-R/midi-to-bdo/releases) page and download:

- **Windows**: `MIDI.to.BDO.exe`
- **Linux**: `MIDI.to.BDO`

No installation or Python required — just run the executable.

## Usage

1. Run the executable
2. Click **Browse** and select a MIDI file
3. Assign BDO instruments to each detected MIDI channel
4. Adjust settings (transpose, velocity, BPM override, etc.) as needed
5. Click **Convert**
6. The output file appears in a `converted/` folder next to the executable

### Owner ID (edit access)

To edit your composition in-game, you need to embed your account's owner ID:

1. Save any composition in BDO's music composer
2. In the converter, click **Load ID from BDO file** and select that saved file
3. Your character name and owner ID will be loaded automatically

BDO music files are stored in:
`Documents/Black Desert/GameOption/musicrecord/`

## Supported Instruments

| Category | Instruments |
|---|---|
| Beginner | Guitar, Flute, Recorder, Hand Drum, Cymbals, Harp, Piano, Violin |
| Florchestra | Acoustic Guitar, Flute, Drum Set, Marnibass, Contrabass, Harp, Piano, Violin, Handpan, Clarinet, Horn |
| Marnian | Wavy Planet, Illusion Tree, Secret Note, Sandwich, Silver Wave, Highway, Hexe Glam |

## Build from source

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python midi2bdo_gui.py
```

To build a standalone executable:

```bash
pip install pyinstaller
python build.py
```

The executable will be in `dist/`.
