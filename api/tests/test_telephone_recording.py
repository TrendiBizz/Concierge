import io
import struct
import wave
from app.telephone_recording import TelephoneRecording
from app.voice_records import audio_type


def test_phone_recording_excludes_preconsent_and_discarded_audio_and_mixes_played_audio():
    clock=[0.0]
    recording=TelephoneRecording(clock=lambda:clock[0])
    recording.append(struct.pack('<hh',30000,30000))
    assert recording.wav() is None
    recording.start()
    recording.append(struct.pack('<hh',20000,-20000))
    recording.append(struct.pack('<hh',20000,-20000))
    clock[0]=.02
    recording.append(struct.pack('<h',1234))
    body=recording.wav()
    assert audio_type('audio/wav',body)=='audio/wav'
    with wave.open(io.BytesIO(body),'rb') as audio:
        assert (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())==(1,2,8000)
        samples=struct.unpack('<161h',audio.readframes(161))
        assert samples[:2]==(32767,-32768) and samples[-1]==1234
    recording.discard()
    recording.append(struct.pack('<h',1))
    assert recording.wav() is None


def test_phone_recording_is_bounded_to_call_limit():
    clock=[0.0]
    recording=TelephoneRecording(clock=lambda:clock[0]);recording.start()
    clock[0]=601
    recording.append(b'\x01\x00'*160)
    assert len(recording.samples)<=recording.LIMIT


def test_phone_wav_rejects_truncated_audio_or_wrong_sample_format():
    import pytest
    from fastapi import HTTPException
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000)
        audio.writeframes(b'\x01\x00'*160)
    with pytest.raises(HTTPException):audio_type('audio/wav',output.getvalue()[:-4])
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(8000)
        audio.writeframes(b'\x01\x00'*160)
    with pytest.raises(HTTPException):audio_type('audio/wav',output.getvalue())
