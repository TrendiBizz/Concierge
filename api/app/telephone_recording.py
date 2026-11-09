"""Bounded, consent-gated capture of audio actually received/played by the PBX."""
from array import array
import io
import sys
import time
import wave


class TelephoneRecording:
    RATE = 8000
    LIMIT = 600 * RATE

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = None
        self.samples = array('h')

    def start(self):
        if self.started is None:
            self.started = self.clock()

    def discard(self):
        self.started = None
        self.samples = array('h')

    def append(self, pcm):
        if self.started is None:
            return
        values = array('h')
        values.frombytes(pcm)
        if sys.byteorder != 'little':
            values.byteswap()
        offset = min(self.LIMIT, max(0, int((self.clock()-self.started)*self.RATE)))
        values = values[:self.LIMIT-offset]
        if not values:
            return
        end = offset + len(values)
        if end > len(self.samples):
            self.samples.extend(array('h', [0]) * (end-len(self.samples)))
        for index, value in enumerate(values, offset):
            self.samples[index] = max(-32768, min(32767, self.samples[index]+value))

    def wav(self):
        if self.started is None or not self.samples:
            return None
        pcm = array('h', self.samples)
        if sys.byteorder != 'little':
            pcm.byteswap()
        output = io.BytesIO()
        with wave.open(output, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(self.RATE)
            audio.writeframes(pcm.tobytes())
        return output.getvalue()
