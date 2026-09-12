package voice

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptrace"
	"net/textproto"
	"strings"
	"time"
)

type HTTPTraceMetrics struct {
	DNS     time.Duration
	Connect time.Duration
	TLS     time.Duration
	TTFB    time.Duration
	Body    time.Duration
	Total   time.Duration
	Reused  bool
}

type Transcriber interface {
	Transcribe(context.Context, []byte) (string, error)
}

type Groq struct {
	APIKey   string
	Model    string
	Language string
	BaseURL  string
	Client   *http.Client
	OnTrace  func(HTTPTraceMetrics)
}

func NewGroq(apiKey, model, language, baseURL string, client *http.Client) Groq {
	if model == "" {
		model = "whisper-large-v3-turbo"
	}
	if language == "" {
		language = "es"
	}
	if baseURL == "" {
		baseURL = "https://api.groq.com/openai/v1"
	}
	if client == nil {
		client = http.DefaultClient
	}
	return Groq{APIKey: apiKey, Model: model, Language: language, BaseURL: baseURL, Client: client}
}

func (g Groq) Transcribe(ctx context.Context, audio []byte) (string, error) {
	return g.TranscribeWithLanguage(ctx, audio, g.Language)
}

// TranscribeWithLanguage is used by offline corpus evaluation to compare
// language selection without changing the production transcriber.
func (g Groq) TranscribeWithLanguage(ctx context.Context, audio []byte, language string) (string, error) {
	if g.APIKey == "" {
		return "", fmt.Errorf("GROQ_API_KEY is not configured")
	}
	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	partHeader := make(textproto.MIMEHeader)
	partHeader.Set("Content-Disposition", `form-data; name="file"; filename="recording.wav"`)
	partHeader.Set("Content-Type", "audio/wav")
	part, err := writer.CreatePart(partHeader)
	if err != nil {
		return "", err
	}
	if _, err := part.Write(audio); err != nil {
		return "", err
	}
	fields := map[string]string{"model": g.Model, "response_format": "json"}
	if strings.TrimSpace(language) != "" {
		fields["language"] = language
	}
	for key, value := range fields {
		if err := writer.WriteField(key, value); err != nil {
			return "", err
		}
	}
	if err := writer.Close(); err != nil {
		return "", err
	}

	started := time.Now()
	var dnsStart, connectStart, tlsStart, firstByte time.Time
	var metrics HTTPTraceMetrics
	trace := &httptrace.ClientTrace{
		DNSStart: func(httptrace.DNSStartInfo) { dnsStart = time.Now() },
		DNSDone: func(httptrace.DNSDoneInfo) {
			if !dnsStart.IsZero() {
				metrics.DNS = time.Since(dnsStart)
			}
		},
		ConnectStart: func(string, string) { connectStart = time.Now() },
		ConnectDone: func(string, string, error) {
			if !connectStart.IsZero() {
				metrics.Connect = time.Since(connectStart)
			}
		},
		TLSHandshakeStart: func() { tlsStart = time.Now() },
		TLSHandshakeDone: func(tls.ConnectionState, error) {
			if !tlsStart.IsZero() {
				metrics.TLS = time.Since(tlsStart)
			}
		},
		GotConn:              func(info httptrace.GotConnInfo) { metrics.Reused = info.Reused },
		GotFirstResponseByte: func() { firstByte = time.Now() },
	}
	req, err := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), http.MethodPost, g.BaseURL+"/audio/transcriptions", &body)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+g.APIKey)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	resp, err := g.Client.Do(req)
	if err != nil {
		if g.OnTrace != nil {
			metrics.Total = time.Since(started)
			g.OnTrace(metrics)
		}
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		message, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		if g.OnTrace != nil {
			metrics.Total = time.Since(started)
			if !firstByte.IsZero() {
				metrics.TTFB = firstByte.Sub(started)
			}
			g.OnTrace(metrics)
		}
		return "", fmt.Errorf("STT returned HTTP %s: %s", resp.Status, bytes.TrimSpace(message))
	}
	var result struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		if g.OnTrace != nil {
			metrics.Total = time.Since(started)
			if !firstByte.IsZero() {
				metrics.TTFB = firstByte.Sub(started)
			}
			if !firstByte.IsZero() {
				metrics.Body = time.Since(firstByte)
			}
			g.OnTrace(metrics)
		}
		return "", err
	}
	metrics.Total = time.Since(started)
	if !firstByte.IsZero() {
		metrics.TTFB = firstByte.Sub(started)
		metrics.Body = time.Since(firstByte)
	}
	if g.OnTrace != nil {
		g.OnTrace(metrics)
	}
	if result.Text == "" {
		return "", fmt.Errorf("STT returned empty text")
	}
	return result.Text, nil
}
