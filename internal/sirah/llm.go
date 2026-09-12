package sirah

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"os"
	"strconv"
	"strings"
	"time"
)

const maxDiagnosticBodyBytes = 16384

const defaultLLMMaxTokens = 4096

const defaultLLMReasoningEffort = "none"

type LLMResponseMetadata struct {
	FinishReason   string
	Usage          string
	ContentPresent bool
	JSONValid      bool
	PromptBytes    int
	InputTokens    int
	OutputTokens   int
}

type HTTPTraceMetrics struct {
	DNS     time.Duration
	Connect time.Duration
	TLS     time.Duration
	TTFB    time.Duration
	Body    time.Duration
	Total   time.Duration
	Reused  bool
}

// LLMStreamTelemetry records streaming milestones without exposing reasoning text.
type LLMStreamTelemetry struct {
	RequestStart           time.Time
	HeadersReceived        time.Time
	FirstSSEEvent          time.Time
	FirstReasoningEvent    time.Time
	FirstContentEvent      time.Time
	FirstSpeechCharacter   time.Time
	FirstStableSpeechChunk time.Time
	StreamComplete         time.Time
	ReasoningPresent       bool
	ReasoningChars         int
	ReasoningTokens        *int
	ConnectionReused       bool
}

// LLMResponseError preserves response diagnostics without including request headers.
type LLMResponseError struct {
	Kind           string
	Status         string
	StatusCode     int
	ContentType    string
	BodyLength     int
	BodyEmpty      bool
	BodyRaw        string
	BodyTruncated  bool
	Choices        int
	ContentPresent bool
	FinishReason   string
	Usage          string
	ResponseFormat string
	Cause          error
}

func (e *LLMResponseError) Error() string {
	return fmt.Sprintf("LLM response %s: status=%q status_code=%d content_type=%q body_length=%d body_empty=%t body_truncated=%t choices=%d content_present=%t finish_reason=%q usage=%s response_format=%s body_raw=%q: %v", e.Kind, e.Status, e.StatusCode, e.ContentType, e.BodyLength, e.BodyEmpty, e.BodyTruncated, e.Choices, e.ContentPresent, e.FinishReason, e.Usage, e.ResponseFormat, e.BodyRaw, e.Cause)
}

func diagnosticBody(body []byte) (string, bool) {
	if len(body) <= maxDiagnosticBodyBytes {
		return string(body), false
	}
	return string(body[:maxDiagnosticBodyBytes]), true
}

func newLLMResponseError(kind string, response *http.Response, body []byte, cause error) *LLMResponseError {
	var status string
	var statusCode int
	var contentType string
	if response != nil {
		status = response.Status
		statusCode = response.StatusCode
		contentType = response.Header.Get("Content-Type")
	}
	raw, truncated := diagnosticBody(body)
	return &LLMResponseError{
		Kind:           kind,
		Status:         status,
		StatusCode:     statusCode,
		ContentType:    contentType,
		BodyLength:     len(body),
		BodyEmpty:      len(body) == 0,
		BodyRaw:        raw,
		BodyTruncated:  truncated,
		ResponseFormat: "json_schema",
		Cause:          cause,
	}
}

type LLM interface {
	Complete(context.Context, Context) (Response, error)
}

// StreamingLLM is optional so existing LLM implementations keep working.
type StreamingLLM interface {
	Stream(context.Context, Context, func(string) error) (Response, error)
}

type OpenAICompatibleLLM struct {
	APIKey          string
	Model           string
	BaseURL         string
	Client          *http.Client
	RequestHeaders  map[string]string
	MaxTokens       int
	ReasoningEffort string
	Temperature     *float64
	OnResponse      func(LLMResponseMetadata)
	OnTrace         func(HTTPTraceMetrics)
	OnStream        func(LLMStreamTelemetry)
}

func (g OpenAICompatibleLLM) applyRequestHeaders(request *http.Request) {
	for name, value := range g.RequestHeaders {
		request.Header.Set(name, value)
	}
}

func NewOpenAICompatibleLLM(apiKey, model, baseURL string, client *http.Client) OpenAICompatibleLLM {
	if model == "" {
		model = "openai/gpt-oss-20b"
	}
	if baseURL == "" {
		baseURL = "https://api.groq.com/openai/v1"
	}
	if client == nil {
		client = http.DefaultClient
	}
	maxTokens := defaultLLMMaxTokens
	if value, err := strconv.Atoi(strings.TrimSpace(os.Getenv("LLM_MAX_TOKENS"))); err == nil && value > 0 {
		maxTokens = value
	}
	reasoningEffort := strings.TrimSpace(os.Getenv("LLM_REASONING_EFFORT"))
	switch reasoningEffort {
	case "none", "low", "medium", "high", "max":
	default:
		reasoningEffort = defaultLLMReasoningEffort
	}
	var temperature *float64
	if raw := strings.TrimSpace(os.Getenv("LLM_TEMPERATURE")); raw != "" {
		if value, err := strconv.ParseFloat(raw, 64); err == nil && value >= 0 && value <= 2 {
			temperature = &value
		}
	}
	return OpenAICompatibleLLM{APIKey: apiKey, Model: model, BaseURL: baseURL, Client: client, MaxTokens: maxTokens, ReasoningEffort: reasoningEffort, Temperature: temperature}
}

func (g OpenAICompatibleLLM) requestPayload(contextData Context, streaming bool) ([]byte, error) {
	if g.plainSpeechModel() {
		contextData.TechnicalContract = NemotronTechnicalContract
	}
	if contextData.TechnicalContract == "" {
		contextData.TechnicalContract = DefaultTechnicalContract
	}
	messages := make([]map[string]string, 0, 2*len(contextData.History)+2)
	if content := contextData.SystemContent(); content != "" {
		messages = append(messages, map[string]string{"role": "system", "content": content})
	}
	for _, turn := range contextData.History {
		if strings.TrimSpace(turn.UserText) == "" || strings.TrimSpace(turn.RobotText) == "" {
			continue
		}
		messages = append(messages, map[string]string{"role": "user", "content": turn.UserText}, map[string]string{"role": "assistant", "content": turn.RobotText})
	}
	if strings.TrimSpace(contextData.UserInput) != "" {
		messages = append(messages, map[string]string{"role": "user", "content": contextData.UserInput})
	}
	schema := map[string]any{"type": "object", "properties": map[string]any{"speech": map[string]string{"type": "string"}, "actions": map[string]any{"type": "array", "items": map[string]any{"type": "string", "enum": []string{"blink", "tired", "nod", "center", "look_at_user", "stop_looking", "follow_person"}}}}, "required": []string{"speech", "actions"}, "additionalProperties": false}
	payload := map[string]any{"model": g.Model, "messages": messages, "temperature": g.temperature(), "reasoning_effort": g.ReasoningEffort}
	if !g.plainSpeechModel() {
		payload["response_format"] = map[string]any{"type": "json_schema", "json_schema": map[string]any{"name": "robot_response", "strict": true, "schema": schema}}
	}
	if g.MaxTokens > 0 {
		payload["max_tokens"] = g.MaxTokens
	}
	if streaming {
		payload["stream"] = true
	}
	return json.Marshal(payload)
}

func (g OpenAICompatibleLLM) plainSpeechModel() bool {
	return strings.TrimSpace(g.Model) == "nemotron-3-nano:30b"
}

// temperature defaults to 0 (deterministic JSON) unless LLM_TEMPERATURE sets
// a value in [0,2]; the schema stays strict either way.
func (g OpenAICompatibleLLM) temperature() float64 {
	if g.Temperature != nil {
		return *g.Temperature
	}
	return 0
}

func (g OpenAICompatibleLLM) Complete(ctx context.Context, contextData Context) (Response, error) {
	if g.APIKey == "" {
		return Response{}, fmt.Errorf("LLM_API_KEY is not configured")
	}
	body, err := g.requestPayload(contextData, false)
	if err != nil {
		return Response{}, err
	}
	promptBytes := len(body)
	started := time.Now()
	var dnsStart, connectStart, tlsStart, firstByte, bodyDone time.Time
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
	req, err := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), http.MethodPost, g.BaseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return Response{}, err
	}
	defer func() {
		metrics.Total = time.Since(started)
		if !firstByte.IsZero() {
			metrics.TTFB = firstByte.Sub(started)
		}
		if !bodyDone.IsZero() && !firstByte.IsZero() {
			metrics.Body = bodyDone.Sub(firstByte)
		}
		if g.OnTrace != nil {
			g.OnTrace(metrics)
		}
	}()
	g.applyRequestHeaders(req)
	req.Header.Set("Authorization", "Bearer "+g.APIKey)
	req.Header.Set("Content-Type", "application/json")
	resp, err := g.Client.Do(req)
	if err != nil {
		return Response{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, readErr := io.ReadAll(resp.Body)
		bodyDone = time.Now()
		if readErr != nil {
			return Response{}, newLLMResponseError("http_read", resp, body, readErr)
		}
		return Response{}, newLLMResponseError("http_error", resp, body, fmt.Errorf("HTTP %s", resp.Status))
	}
	body, err = io.ReadAll(resp.Body)
	bodyDone = time.Now()
	if err != nil {
		return Response{}, newLLMResponseError("body_read", resp, body, err)
	}
	var result struct {
		Choices []struct {
			Message struct {
				Content *string `json:"content"`
			} `json:"message"`
			FinishReason *string `json:"finish_reason"`
		} `json:"choices"`
		Usage json.RawMessage `json:"usage"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return Response{}, newLLMResponseError("json_decode", resp, body, err)
	}
	if len(result.Choices) == 0 {
		diagnostic := newLLMResponseError("no_choices", resp, body, fmt.Errorf("LLM returned no choices"))
		diagnostic.Usage = usageDiagnostic(result.Usage)
		return Response{}, diagnostic
	}
	choice := result.Choices[0]
	diagnostic := newLLMResponseError("content_decode", resp, body, nil)
	diagnostic.Choices = len(result.Choices)
	diagnostic.ContentPresent = choice.Message.Content != nil
	diagnostic.FinishReason = stringDiagnostic(choice.FinishReason)
	diagnostic.Usage = usageDiagnostic(result.Usage)
	if choice.Message.Content == nil || strings.TrimSpace(*choice.Message.Content) == "" {
		diagnostic.Cause = fmt.Errorf("LLM returned no content")
		return Response{}, diagnostic
	}
	if g.plainSpeechModel() {
		if g.OnResponse != nil {
			inputTokens, outputTokens := usageCounts(result.Usage)
			g.OnResponse(LLMResponseMetadata{FinishReason: diagnostic.FinishReason, Usage: diagnostic.Usage, ContentPresent: true, JSONValid: true, PromptBytes: promptBytes, InputTokens: inputTokens, OutputTokens: outputTokens})
		}
		return Response{Speech: strings.TrimSpace(*choice.Message.Content), Actions: []Action{}}, nil
	}
	var response Response
	content := unwrapJSONFence(*choice.Message.Content)
	if err := json.Unmarshal([]byte(content), &response); err != nil {
		if g.OnResponse != nil {
			inputTokens, outputTokens := usageCounts(result.Usage)
			g.OnResponse(LLMResponseMetadata{FinishReason: diagnostic.FinishReason, Usage: diagnostic.Usage, ContentPresent: true, PromptBytes: promptBytes, InputTokens: inputTokens, OutputTokens: outputTokens})
		}
		diagnostic.Cause = fmt.Errorf("decode LLM response: %w", err)
		return Response{}, diagnostic
	}
	if g.OnResponse != nil {
		inputTokens, outputTokens := usageCounts(result.Usage)
		g.OnResponse(LLMResponseMetadata{FinishReason: diagnostic.FinishReason, Usage: diagnostic.Usage, ContentPresent: true, JSONValid: true, PromptBytes: promptBytes, InputTokens: inputTokens, OutputTokens: outputTokens})
	}
	return response, nil
}

// unwrapJSONFence accepts only one outer Markdown fence. It does not repair or
// search through arbitrary model output.
func unwrapJSONFence(content string) string {
	content = strings.TrimSpace(content)
	if !strings.HasPrefix(content, "```") || !strings.HasSuffix(content, "```") {
		return content
	}
	lines := strings.Split(content, "\n")
	if len(lines) < 3 || !strings.HasPrefix(lines[0], "```") || lines[len(lines)-1] != "```" {
		return content
	}
	return strings.TrimSpace(strings.Join(lines[1:len(lines)-1], "\n"))
}

func usageCounts(value json.RawMessage) (int, int) {
	var usage struct {
		PromptTokens     int `json:"prompt_tokens"`
		CompletionTokens int `json:"completion_tokens"`
		InputTokens      int `json:"input_tokens"`
		OutputTokens     int `json:"output_tokens"`
	}
	if err := json.Unmarshal(value, &usage); err != nil {
		return 0, 0
	}
	input := usage.PromptTokens
	if input == 0 {
		input = usage.InputTokens
	}
	output := usage.CompletionTokens
	if output == 0 {
		output = usage.OutputTokens
	}
	return input, output
}

func stringDiagnostic(value *string) string {
	if value == nil {
		return "<missing>"
	}
	return *value
}

func usageDiagnostic(value json.RawMessage) string {
	if len(value) == 0 || string(value) == "null" {
		return "<missing>"
	}
	return string(value)
}
