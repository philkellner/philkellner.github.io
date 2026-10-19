# drumchart

Song -> isolated drums -> practice chart for the Drum Trainer at `/drums`.

```bash
pip install numpy demucs      # plus ffmpeg on PATH
python tools/drumchart/drumchart.py "my song.mp3" -o out/
```

Produces in `out/`: `chart.json`, `chart.mid`, `drums.wav` (isolated stem), `backing.wav` (song minus drums).

Open `/drums` (or `drums/index.html`), load `chart.json`, and load `backing.wav` as the audio to play along with.
Use the full song instead if you want to hear the original drums.

Tuning (check the result with "Hear the chart" in the trainer, then adjust):
- `--sens 0.7` finds more hits, `--sens 1.5` fewer
- `--gate 0.5` keeps quieter/ghost notes, `--gate 0.9` only the loud ones
- `--bpm 128` overrides tempo detection (half/double-time errors are common)
- `--no-quantize` keeps the drummer's real timing instead of snapping to a 16th grid

Limits: three lanes (kick, snare, hi-hat; cymbals/toms are folded into those). Onsets are classified by frequency band,
so busy fills and open hats can be misread. `chart.mid` can be edited in a DAW if you want to fix a part by hand.
Keep audio files local: the app reads them in the browser and nothing is uploaded or committed.
