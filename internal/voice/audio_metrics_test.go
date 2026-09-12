package voice

import (
	"bytes"
	"encoding/binary"
	"testing"
)

func TestWAVHeaderAndPayload(t *testing.T) {
	pcm := make([]byte, 640)
	for i := 0; i < len(pcm); i += 2 {
		binary.LittleEndian.PutUint16(pcm[i:i+2], uint16(int16(i)))
	}
	wav := wavBytes(pcm, 16000)
	info, err := InspectWAV(wav)
	if err != nil {
		t.Fatal(err)
	}
	if info.AudioFormat != 1 || info.Channels != 1 || info.SampleRate != 16000 || info.BitsPerSample != 16 || info.ByteRate != 32000 || info.BlockAlign != 2 {
		t.Fatalf("unexpected WAV info: %+v", info)
	}
	if len(wav) != 44+len(pcm) || !bytes.Equal(info.Data, pcm) {
		t.Fatal("WAV payload was changed")
	}
}

func TestMeasureWAV(t *testing.T) {
	pcm := make([]byte, 16000*2)
	for i := 1600; i < 14400; i++ {
		binary.LittleEndian.PutUint16(pcm[i*2:i*2+2], uint16(int16(1000)))
	}
	metrics, err := MeasureWAV(wavBytes(pcm, 16000))
	if err != nil {
		t.Fatal(err)
	}
	if metrics.Peak != 1000 || metrics.ClippedSamples != 0 || metrics.LeadingSilenceMS != 100 || metrics.TrailingSilenceMS != 100 {
		t.Fatalf("unexpected metrics: %+v", metrics)
	}
}
