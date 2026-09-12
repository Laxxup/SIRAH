package voice

const (
	audioSampleRate  = 48000
	audioFrameBytes  = 480 * 2
	webrtcFrameBytes = audioFrameBytes
)

func frameBytesForRate(sampleRate int) int {
	return sampleRate / 100 * 2
}
