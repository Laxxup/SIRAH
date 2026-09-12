package voice

import "testing"

func TestFrameBytesForRate(t *testing.T) {
	for _, test := range []struct {
		rate int
		want int
	}{
		{rate: 16000, want: 320},
		{rate: 48000, want: 960},
	} {
		if got := frameBytesForRate(test.rate); got != test.want {
			t.Fatalf("frameBytesForRate(%d) = %d, want %d", test.rate, got, test.want)
		}
	}
}
