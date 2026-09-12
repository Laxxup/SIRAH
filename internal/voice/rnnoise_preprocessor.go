//go:build rnnoise

package voice

/*
#cgo pkg-config: rnnoise soxr
#include <rnnoise.h>
#include <soxr.h>

static soxr_error_t sirah_soxr_process(soxr_t resampler, void *input, size_t input_len, size_t *input_done, void *output, size_t output_len, size_t *output_done) {
    return soxr_process(resampler, (soxr_in_t)input, input_len, input_done, (soxr_out_t)output, output_len, output_done);
}

static soxr_t sirah_soxr_create(soxr_error_t *error) {
    soxr_io_spec_t io = soxr_io_spec(SOXR_INT16_I, SOXR_INT16_I);
    io.flags = SOXR_NO_DITHER;
    return soxr_create(48000, 16000, 1, error, &io, NULL, NULL);
}
*/
import "C"

import (
	"encoding/binary"
	"fmt"
	"math"
	"runtime"
	"unsafe"
)

const (
	rnnoiseRate       = 48000
	rnnoiseFrameBytes = 480 * 2
	sttRate           = 16000
)

type RNNoisePreprocessor struct {
	state     *C.DenoiseState
	resampler C.soxr_t
}

func NewRNNoisePreprocessor() (*RNNoisePreprocessor, error) {
	state := C.rnnoise_create(nil)
	if state == nil {
		return nil, fmt.Errorf("rnnoise_create failed")
	}
	var resampleErr C.soxr_error_t
	resampler := C.sirah_soxr_create(&resampleErr)
	if resampler == nil {
		C.rnnoise_destroy(state)
		return nil, fmt.Errorf("soxr_create: %s", cError(resampleErr))
	}
	preprocessor := &RNNoisePreprocessor{state: state, resampler: resampler}
	runtime.SetFinalizer(preprocessor, (*RNNoisePreprocessor).Close)
	return preprocessor, nil
}

func (p *RNNoisePreprocessor) Name() string    { return "rnnoise+soxr" }
func (p *RNNoisePreprocessor) InputRate() int  { return rnnoiseRate }
func (p *RNNoisePreprocessor) OutputRate() int { return sttRate }

func (p *RNNoisePreprocessor) Process(input []byte) ([]byte, error) {
	if p.state == nil || p.resampler == nil {
		return nil, fmt.Errorf("RNNoise preprocessor is closed")
	}
	if len(input) != rnnoiseFrameBytes {
		return nil, fmt.Errorf("RNNoise requires %d-byte 48 kHz frames, got %d", rnnoiseFrameBytes, len(input))
	}
	denoised := make([]float32, 480)
	for i := range denoised {
		value := int16(binary.LittleEndian.Uint16(input[i*2 : i*2+2]))
		denoised[i] = float32(value) / 32768
	}
	output := make([]float32, 480)
	C.rnnoise_process_frame(p.state, (*C.float)(unsafe.Pointer(&output[0])), (*C.float)(unsafe.Pointer(&denoised[0])))
	pcm := make([]int16, len(output))
	for i, sample := range output {
		value := int(math.Round(float64(sample * 32768)))
		if value > 32767 {
			value = 32767
		}
		if value < -32768 {
			value = -32768
		}
		pcm[i] = int16(value)
	}
	resampled := make([]int16, 320)
	var idone, odone C.size_t
	resampleErr := C.sirah_soxr_process(p.resampler, unsafe.Pointer(&pcm[0]), C.size_t(len(pcm)), &idone, unsafe.Pointer(&resampled[0]), C.size_t(len(resampled)), &odone)
	if resampleErr != nil {
		return nil, fmt.Errorf("soxr_process: %s", cError(resampleErr))
	}
	if int(idone) != len(pcm) {
		return nil, fmt.Errorf("soxr consumed %d of %d samples", idone, len(pcm))
	}
	bytes := make([]byte, int(odone)*2)
	for i, sample := range resampled[:int(odone)] {
		binary.LittleEndian.PutUint16(bytes[i*2:i*2+2], uint16(sample))
	}
	return bytes, nil
}

func (p *RNNoisePreprocessor) Close() error {
	runtime.SetFinalizer(p, nil)
	if p.resampler != nil {
		C.soxr_delete(p.resampler)
		p.resampler = nil
	}
	if p.state != nil {
		C.rnnoise_destroy(p.state)
		p.state = nil
	}
	return nil
}

func cError(err C.soxr_error_t) string {
	if err == nil {
		return "unknown error"
	}
	return C.GoString(err)
}
