package sirah

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"strings"
	"time"
	"unicode/utf8"
)

// speechStreamParser extracts only the speech JSON string from streamed JSON.
// It deliberately never forwards the enclosing JSON or the actions field.
type speechStreamParser struct {
	raw     strings.Builder
	value   strings.Builder
	emitted int
	done    bool
}

func (p *speechStreamParser) Feed(fragment string, emit func(string) error) error {
	p.raw.WriteString(fragment)
	if p.done {
		return nil
	}
	raw := p.raw.String()
	p.value.Reset()
	trimmed := strings.TrimSpace(raw)
	if strings.HasPrefix(trimmed, "```") {
		lineEnd := strings.IndexByte(trimmed, '\n')
		if lineEnd < 0 {
			return nil
		}
		trimmed = strings.TrimSpace(trimmed[lineEnd+1:])
	}
	if !strings.HasPrefix(trimmed, "{") {
		return nil
	}
	start := strings.Index(raw, `"speech"`)
	if start < 0 {
		return nil
	}
	colon := strings.IndexByte(raw[start+len(`"speech"`):], ':')
	if colon < 0 {
		return nil
	}
	index := start + len(`"speech"`) + colon + 1
	for index < len(raw) && (raw[index] == ' ' || raw[index] == '\n' || raw[index] == '\r' || raw[index] == '\t') {
		index++
	}
	if index >= len(raw) || raw[index] != '"' {
		return nil
	}
	index++
	for index < len(raw) {
		if raw[index] == '"' {
			p.done = true
			break
		}
		if raw[index] == '\\' {
			if index+1 >= len(raw) {
				break
			}
			end := index + 2
			if raw[index+1] == 'u' {
				end = index + 6
			}
			if end > len(raw) {
				break
			}
			var decoded string
			if err := json.Unmarshal([]byte(`"`+raw[index:end]+`"`), &decoded); err != nil {
				break
			}
			p.value.WriteString(decoded)
			index = end
			continue
		}
		p.value.WriteByte(raw[index])
		index++
	}
	value := p.value.String()
	if !utf8.ValidString(value) {
		value = strings.ToValidUTF8(value, "")
	}
	if len(value) > p.emitted {
		if err := emit(value[p.emitted:]); err != nil {
			return err
		}
		p.emitted = len(value)
	}
	return nil
}

func (g OpenAICompatibleLLM) Stream(ctx context.Context, contextData Context, emit func(string) error) (Response, error) {
	if g.APIKey == "" {
		return Response{}, fmt.Errorf("LLM_API_KEY is not configured")
	}
	if emit == nil {
		return Response{}, fmt.Errorf("LLM stream callback is nil")
	}
	body, err := g.requestPayload(contextData, true)
	if err != nil {
		return Response{}, err
	}
	telemetry := LLMStreamTelemetry{RequestStart: time.Now()}
	var firstByte time.Time
	var traceMetrics HTTPTraceMetrics
	defer func() {
		traceMetrics.Total = time.Since(telemetry.RequestStart)
		if !firstByte.IsZero() {
			traceMetrics.TTFB = firstByte.Sub(telemetry.RequestStart)
		}
		traceMetrics.Reused = telemetry.ConnectionReused
		if g.OnTrace != nil {
			g.OnTrace(traceMetrics)
		}
		if g.OnStream != nil {
			g.OnStream(telemetry)
		}
	}()
	trace := &httptrace.ClientTrace{
		GotConn:              func(info httptrace.GotConnInfo) { telemetry.ConnectionReused = info.Reused },
		GotFirstResponseByte: func() { firstByte = time.Now() },
	}
	req, err := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), http.MethodPost, g.BaseURL+"/chat/completions", strings.NewReader(string(body)))
	if err != nil {
		return Response{}, err
	}
	g.applyRequestHeaders(req)
	req.Header.Set("Authorization", "Bearer "+g.APIKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	resp, err := g.Client.Do(req)
	if err != nil {
		return Response{}, err
	}
	telemetry.HeadersReceived = time.Now()
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		errBody, _ := io.ReadAll(io.LimitReader(resp.Body, maxDiagnosticBodyBytes))
		return Response{}, newLLMResponseError("http_error", resp, errBody, fmt.Errorf("HTTP %s", resp.Status))
	}
	var content strings.Builder
	parser := &speechStreamParser{}
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "[DONE]" {
			break
		}
		if telemetry.FirstSSEEvent.IsZero() {
			telemetry.FirstSSEEvent = time.Now()
		}
		var event struct {
			Choices []struct {
				Delta struct {
					Content          *string `json:"content"`
					ReasoningContent *string `json:"reasoning_content"`
					Reasoning        *string `json:"reasoning"`
				} `json:"delta"`
			} `json:"choices"`
			Usage struct {
				CompletionTokens int `json:"completion_tokens"`
				OutputTokens     int `json:"output_tokens"`
			} `json:"usage"`
		}
		if err := json.Unmarshal([]byte(data), &event); err != nil {
			return Response{}, fmt.Errorf("decode SSE event: %w", err)
		}
		if len(event.Choices) == 0 {
			continue
		}
		reasoning := event.Choices[0].Delta.ReasoningContent
		if reasoning == nil {
			reasoning = event.Choices[0].Delta.Reasoning
		}
		if reasoning != nil {
			if telemetry.FirstReasoningEvent.IsZero() {
				telemetry.FirstReasoningEvent = time.Now()
			}
			telemetry.ReasoningPresent = true
			telemetry.ReasoningChars += len([]rune(*reasoning))
		}
		if event.Choices[0].Delta.Content == nil {
			continue
		}
		fragment := *event.Choices[0].Delta.Content
		if strings.TrimSpace(fragment) != "" && telemetry.FirstContentEvent.IsZero() {
			telemetry.FirstContentEvent = time.Now()
		}
		content.WriteString(fragment)
		if g.plainSpeechModel() {
			if fragment != "" {
				if telemetry.FirstSpeechCharacter.IsZero() {
					telemetry.FirstSpeechCharacter = time.Now()
				}
				if err := emit(fragment); err != nil {
					return Response{}, err
				}
			}
			continue
		}
		if err := parser.Feed(fragment, func(value string) error {
			if telemetry.FirstSpeechCharacter.IsZero() && value != "" {
				telemetry.FirstSpeechCharacter = time.Now()
			}
			return emit(value)
		}); err != nil {
			return Response{}, err
		}
	}
	if err := scanner.Err(); err != nil {
		return Response{}, err
	}
	telemetry.StreamComplete = time.Now()
	var response Response
	if g.plainSpeechModel() {
		if strings.TrimSpace(content.String()) == "" {
			return Response{}, fmt.Errorf("Nemotron returned empty speech")
		}
		telemetry.StreamComplete = time.Now()
		if g.OnResponse != nil {
			g.OnResponse(LLMResponseMetadata{ContentPresent: true, JSONValid: true, PromptBytes: len(body)})
		}
		return Response{Speech: strings.TrimSpace(content.String()), Actions: []Action{}}, nil
	}
	if err := json.Unmarshal([]byte(unwrapJSONFence(content.String())), &response); err != nil {
		return Response{}, fmt.Errorf("decode streamed response: %w", err)
	}
	if err := ValidateResponse(response); err != nil {
		return Response{}, err
	}
	if g.OnResponse != nil {
		g.OnResponse(LLMResponseMetadata{ContentPresent: true, JSONValid: true, PromptBytes: len(body)})
	}
	return response, nil
}
