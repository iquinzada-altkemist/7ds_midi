# Copyright (c) 2020 /u/Provalist

import argparse
from collections import OrderedDict

from mido import MidiFile, merge_tracks


class Note:
    _PITCHES = [
        'C', 'C#', # Meliodas
        'D', 'D#', # Diane
        'E',       # Ban
        'F', 'F#', # King
        'G', 'G#', # Gowther
        'A', 'A#', # Merlin
        'B'        # Escanor
    ]

    def __init__(self, msg, start, duration, disable_vel=False):
        self.note_value = msg.note
        self.pitch = self._PITCHES[msg.note % 12]

        self.octave = msg.note // 12 - 1 # Divide by 12 to get the octave. Translate down by 1 too.
        self.start = start # Time (in sixteenth notes) since the beginning of the track that this note starts on
        self.duration = duration # Duration of the note in sixteenth notes
        self.velocity = 12 if disable_vel else round(msg.velocity * (16/128)) # Note velocity, linearly scaled from 0-127 to 0-15

    def _get_length_str(self, duration):
        assert duration >= 1, f"Error: Note duration was less than a sixteenth note. ({duration})"

        d = OrderedDict()
        d[1] = '16' # 1
        d[2] = '8' # 2 = 1 eighth note
        d[3] = '8.' # 3 = 1.5 eighth = dotted eighth
        d[4] = '' # 4 = quarter note = blank by default
        d[6] = '4.' # 6 = 1.5 quarter = dotted quarter
        d[8] = '2' # 8 = half note
        d[12] = '2.' # 12 = 1.5 half = dotted half
        d[16] = '1' # 16 = whole note
        d[24] = '1.' # 24 = 1.5 whole = dotted whole
        result = d.get(duration)

        if not result:
            # Find the largest known unit in the dict and append it to the result.
            low = None
            for key in reversed(d):
                if key < duration:
                    low = key
                    break

            # Take remaining duration and recursively append the rest.
            return d[low] + f'&{self.pitch}' + self._get_length_str(duration - low)

        return result

    def encode(self):
        if self.duration <= 0: return '' # Note with 0 duration. Happens sometimes I guess. Just ignore it.
        result = ''

        # Add velocity
        if self.velocity != 12: result += 'V' + str(self.velocity)

        # Add octave information
        result += 'O' + str(self.octave)

        # Add pitch (note symbol)
        result += self.pitch

        # Add the length of the note
        result += self._get_length_str(self.duration)

        return result

    @property
    def end(self):
        return self.start + self.duration


class Rest(Note):
    def __init__(self, start, duration):
        self.pitch = 'R' # It means Rest. Pretty easy to figure out tbh
        self.start = start # See Note.start
        self.duration = duration # See Note.duration

    def encode(self):
        return self.pitch + self._get_length_str(self.duration)

    @property
    def end(self):
        return self.start + self.duration


class Track:
    def __init__(self, track, ticks_per_beat, disable_vel, speed_mult):
        self.track = track # Mido track object
        self.tpb = ticks_per_beat * speed_mult # Time ticks per beat. Speed mult > 1 goes faster and < 1 goes slower.
        self._disable_vel = disable_vel

    @staticmethod
    def _get_available_line(lines, note):
        """ Gets the most recent available line for a note. "Available" here
            means the start of the note is after the end of the line, so the
            whole line is linearly sequential. If no line is available, a
            new one will be added. """
        for line in reversed(lines):
            if line.end <= note.start:
                return line

        # No available line found
        new_line = Line(note.start)
        lines.append(new_line)
        return new_line

    def encode(self):
        result = ''

        durations = {}
        lines = []
        time = 0

        for msg in self.track:
            time += self._tick_to_sixteenth(msg.time)  # increase global time counter
            # Increase duration for all active notes
            for k in durations:
                for note in durations[k]:
                    note.duration += self._tick_to_sixteenth(msg.time)

            if msg.type in ('note_on', 'note_off'): # Ignore all other message types. I dunno if they're actually useful.
                if msg.type == 'note_on' and msg.velocity > 0: # some midi files use note_on with velocity = 0 to mean note_off
                    # Note on
                    if msg.note not in durations:
                        durations[msg.note] = []
                    durations[msg.note].append(Note(msg, time, 0, disable_vel=self._disable_vel))
                else:
                    # Note off
                    note = durations[msg.note].pop()
                    self._get_available_line(lines, note).append(note)

        # Encode all lines and join them with a comma
        result += ','.join(line.encode() for line in lines)

        return result

    def _tick_to_sixteenth(self, ticks):
        """ Convert a number of ticks into an equivalent number of sixteenth notes,
            roughly. Grand cross does not support less than 16th notes for some reason.
            *angry triplet noises* """
        return round((ticks / self.tpb) * 4)

class Line(list):
    def __init__(self, start):
        super().__init__()
        self.start = start
        self.duration = 0
        # If the line doesn't start at the beginning, add a rest from the beginning
        # to the start of the line
        if start > 0:
            super().append(Rest(0, start))

    def append(self, note):
        if note.start > self.end:
            # Space between notes in this line, add a rest between them.
            super().append(Rest(self.end, note.start - self.end))
            self.duration += note.start - self.end

        # Add note to the line
        super().append(note)

        # Increase line duration
        self.duration += note.duration

    def encode(self):
        # Encode all notes
        return ''.join(note.encode() for note in self)

    @property
    def end(self):
        return self.start + self.duration

class Midi:
    def __init__(self, filename, tempo, disable_vel, speed_mult):
        """
        Convert a .midi (or .mid) file into an MML code (mostly) usable by the Jukebox in 7 Deadly Sins: Grand Cross

        :param filename: Filepath to the midi
        :param tempo: Tempo in BPM
        :param disable_vel: Disables note velocity so all notes are the same volume.
        :param speed_mult: Use this to scale the lengths of all the notes. Greater than one speeds up
        the song and less than 1 slows it down. For example, if speed_mult = 0.5, all quarter notes
        become halves, etc. If speed_mult is 2.0, all quarter notes become eighth notes. Since GC only
        supports a minimum of 16th notes, this might come in handy if your MIDI has a bunch of 64th
        notes or some shit I don't know.
        """
        self.midi = MidiFile(filename)
        self.tempo = tempo
        self.track = Track(
            merge_tracks(self.midi.tracks),
            self.midi.ticks_per_beat,
            disable_vel,
            speed_mult
        )

    def encode(self):
        result = '7ML@' # No idea what this means. Maybe the 7 is for 7 deadly sins and ML is Macro Language?
        if self.tempo != 120: result += 'T' + str(self.tempo) # Add tempo
        result += self.track.encode() + ';' # Encode the combined track
        return result


def lmao(n):
    import random
    print(' '.join(random.choice(('demi', 'hemi', 'semi')) for _ in range(n)) + ' quaver')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert a .midi (or .mid) file into an MML code (mostly) usable by the Jukebox in 7 Deadly Sins: Grand Cross.')
    parser.add_argument('filepath', type=str, help='Path to your midi file')
    parser.add_argument('--tempo', '-t', type=int, help='Song tempo (BPM). Note that the tempo in the midi file may not sound the same when imported into GC.')
    parser.add_argument('--disable_vel', '-dv', action='store_true', help='Disables note velocity, so all notes have the same volume.')
    parser.add_argument('--speed_mult', '-sm', type=float, help='Scale the duration of all notes. Lower than 1 = slower, greater than 1 = faster. Ex, 2.0 turns halves into quarters, quarters into eighths, etc.')

    args = parser.parse_args()
    midi = Midi(
        args.filepath,
        args.tempo or 120,
        args.disable_vel or False,
        args.speed_mult or 1.0
    )
    print('Successfully loaded midi and merged tracks. Encoding now! :O')
    print("This shouldn't take more than like 5 seconds so if it feels like its taking forever you're probably fucked lmao")
    print()
    encoded = midi.encode()
    print(encoded)
    print()
    print(f'Character length: {len(encoded)}')
    print('Note: This code is probably over 3 times longer than what is generated in-game. Be sure to import this into the game and copy it again '
          'before sharing it somewhere else. It must be under 4000 characters to be saved (it can still be imported at any length though).')
