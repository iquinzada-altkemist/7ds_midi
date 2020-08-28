# 7ds_midi
MIDI music converter for 7DS: Grand Cross by u/provalist

Usage: `python 7ds_midi.py filename.mid`

Optional Arguments: 
  * `--tempo n` sets the tempo in BPM (default is 120)
  * `--disable_vel` disables note velocities (default is False)
  * `--speed_mult n` scales note durations (default is 1.0)
  
See `python 7ds_midi.py --help` for more info

This requires the `mido` MIDI library to run. Do `pip install mido` before using.
