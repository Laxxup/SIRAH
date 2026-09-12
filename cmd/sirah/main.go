package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/Laxxup/SIRAH/internal/firmware"
	"github.com/Laxxup/SIRAH/internal/motion"
	"github.com/Laxxup/SIRAH/internal/sirah"
	"github.com/Laxxup/SIRAH/internal/vision"
	"github.com/Laxxup/SIRAH/internal/voice"
	"github.com/getzep/zep-go/v3/client"
	"github.com/getzep/zep-go/v3/option"
)

func main() {
	os.Exit(run())
}

func run() (exitCode int) {
	loadDotEnv(".env")
	runCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	debug := flag.Bool("debug", false, "show runtime diagnostics")
	voiceMode := flag.Bool("voice", false, "run hands-free voice mode")
	preview := flag.Bool("preview", false, "enable camera preview (needs OpenCV and a display; Q exits SIRAH)")
	selftest := flag.Bool("selftest", false, "run deterministic hardware self-test and exit")
	flag.Usage = func() {
		fmt.Fprintln(flag.CommandLine.Output(), "S.I.R.A.H. — Sistema Inteligente Robótico de Asistencia Humana\n\nText mode by default: one stdin line per turn, replies on stdout.\nSet LLM_API_KEY; no audio tools are required for text. Ctrl+C or Ctrl+D exits.\nUse -voice for microphone input and Piper speech (requires GROQ_API_KEY).\n-selftest requires configured ESP32 hardware and a camera; it moves servos.\n\nOptions:")
		flag.PrintDefaults()
		fmt.Fprintln(flag.CommandLine.Output(), "\nExamples:\n  CGO_ENABLED=0 go run ./cmd/sirah\n  go run ./cmd/sirah -voice -preview\n  go run -tags opencv5 ./cmd/sirah -voice -preview   # OpenCV 5 opt-in")
	}
	flag.Parse()
	if flag.NArg() != 0 {
		fmt.Fprintf(os.Stderr, "SIRAH: unexpected positional arguments: %q; use -h for help\n", flag.Args())
		return 2
	}
	if *selftest {
		return runSelftest(runCtx, *debug)
	}
	if strings.TrimSpace(os.Getenv("LLM_API_KEY")) == "" {
		fmt.Fprintln(os.Stderr, "SIRAH: set LLM_API_KEY in .env or the environment to start a conversation")
		return 1
	}
	if *voiceMode && strings.TrimSpace(os.Getenv("GROQ_API_KEY")) == "" {
		fmt.Fprintln(os.Stderr, "SIRAH: -voice requires GROQ_API_KEY for speech transcription")
		return 1
	}

	// Only physically effective actions are announced. nod is accepted by the
	// firmware but moves nothing yet; follow_person needs a real person
	// detector (vision only sees faces). Enums and routes stay for the future.
	actions := []sirah.Action{sirah.ActionBlink, sirah.ActionTired, sirah.ActionCenter, sirah.ActionLookAtUser, sirah.ActionStopLooking}
	contextData, err := sirah.LoadContext("config/persona", actions)
	if err != nil {
		fmt.Printf("Context: WARNING - %s\n", err)
	}

	local := sirah.NewLocalMemory(envInt("AGENT_HISTORY_LIMIT", 12))
	var memory sirah.Memory = local
	var hybrid *sirah.HybridMemory
	if key := strings.TrimSpace(os.Getenv("ZEP_API_KEY")); key != "" {
		zep := client.NewClient(option.WithAPIKey(key))
		hybrid = sirah.NewHybridMemory(local, sirah.NewZepMemory(zep), func(err error) { fmt.Printf("Memory: WARNING - Zep: %s\n", err) })
		memory = hybrid
	}
	if hybrid != nil {
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			if err := hybrid.Close(shutdownCtx); err != nil {
				fmt.Printf("Memory: WARNING - shutdown: %s\n", err)
			}
		}()
	}

	httpClient := &http.Client{}
	var contextTiming sirah.ContextTiming
	var llmMetadata sirah.LLMResponseMetadata
	var streamTelemetry sirah.LLMStreamTelemetry
	var ollamaTrace sirah.HTTPTraceMetrics
	sessionID := envString("AGENT_SESSION_ID", "default")
	llm := sirah.NewOpenAICompatibleLLM(os.Getenv("LLM_API_KEY"), os.Getenv("LLM_MODEL"), os.Getenv("LLM_BASE_URL"), httpClient)
	llm.RequestHeaders = providerRequestHeaders(llm.BaseURL, sessionID)
	llm.OnResponse = func(metadata sirah.LLMResponseMetadata) { llmMetadata = metadata }
	llm.OnStream = func(telemetry sirah.LLMStreamTelemetry) { streamTelemetry = telemetry }
	llm.OnTrace = func(metrics sirah.HTTPTraceMetrics) {
		ollamaTrace = metrics
		if *debug {
			fmt.Printf("[NETWORK LLM]\ndns_ms=%.1f\nconnect_ms=%.1f\ntls_ms=%.1f\nconnection_reused=%t\nttfb_ms=%.1f\nbody_ms=%.1f\ntotal_ms=%.1f\n", ms(metrics.DNS), ms(metrics.Connect), ms(metrics.TLS), metrics.Reused, ms(metrics.TTFB), ms(metrics.Body), ms(metrics.Total))
		}
	}
	robot := sirah.Agent{Context: contextData, AvailableActions: actions, LLM: llm, ConversationStore: memory, SessionID: sessionID, UserID: envString("AGENT_USER_ID", "local-user"), HistoryLimit: envInt("AGENT_HISTORY_LIMIT", 12), Timeout: envDuration("LLM_TIMEOUT", 90*time.Second)}
	robot.WakeupStyle = contextData.WakeupStyle
	robot.ContextTiming = func(timing sirah.ContextTiming) { contextTiming = timing }
	var llmDuration time.Duration
	robot.LLMDuration = func(value time.Duration) { llmDuration = value }
	perception := vision.NewSnapshotStore()

	var device firmware.Device = firmware.Unavailable{}
	serialFile := openSerial(os.Getenv("FIRMWARE_SERIAL"), envInt("FIRMWARE_BAUD", 115200))
	var serialDevice *firmware.Serial
	if serialFile != nil {
		serialDevice = firmware.NewSerial(serialFile)
		defer serialDevice.Close()
		serialDevice.Reader = serialFile
		if err := serialDevice.Start(runCtx); err != nil {
			fmt.Printf("Firmware: WARNING - reader: %s\n", err)
		} else if err := handshakeFirmware(runCtx, serialDevice); err != nil {
			fmt.Printf("Firmware: WARNING - handshake: %s\n", err)
		} else {
			device = serialDevice
		}
	}
	mot := motion.New(device)
	firmwareEventsDone := make(chan struct{})
	if serialDevice == nil {
		close(firmwareEventsDone)
	} else {
		go func() {
			defer close(firmwareEventsDone)
			runFirmwareEvents(runCtx, serialDevice.Events(), mot)
		}()
	}
	defer func() {
		stop()
		<-firmwareEventsDone
	}()
	targetUpdates := make(chan vision.Target, 1)
	targetDone := make(chan struct{})
	go func() {
		defer close(targetDone)
		runVisionTargets(runCtx, targetUpdates, mot, *debug)
	}()
	defer func() { <-targetDone }()
	visionDone := make(chan struct{})
	visionStarted := false
	visionEnabled := visionShouldStart(*preview)
	runVision := func() {
		defer close(visionDone)
		if !visionEnabled {
			return
		}
		visionConfig := vision.DefaultConfig(envString("VISION_MODEL", "models/face_detection_yunet_2023mar.onnx"))
		visionConfig.CameraIndex = envInt("VISION_CAMERA_INDEX", 0)
		visionConfig.Preview = *preview
		visionTracker := vision.NewTemporalTracker(vision.DefaultTrackerConfig())
		err := vision.RunCamera(runCtx, visionConfig, visionTracker, perception.Publish, func(target vision.Target) {
			vision.PublishLatestTarget(targetUpdates, target)
		}, func(sample vision.DebugSample) {
			if !*debug {
				return
			}
			fmt.Printf("Vision: faces=%d raw_target=%s smooth_target=%s vision_ms=%.1f read_ms=%.1f detect_ms=%.1f\n", sample.Snapshot.FaceCount, formatTarget(sample.RawTarget), formatTarget(sample.SmoothTarget), ms(sample.Read)+ms(sample.Detect), ms(sample.Read), ms(sample.Detect))
		})
		if err != nil && runCtx.Err() == nil {
			fmt.Printf("Vision: WARNING - DEGRADED: %s\n", err)
			return
		}
		// Q in the preview window ends RunCamera cleanly: stop the app too.
		if *preview && runCtx.Err() == nil {
			fmt.Printf("Vision: preview closed, shutting down\n")
			stop()
		}
	}
	defer func() {
		stop()
		if !visionStarted {
			return
		}
		select {
		case <-visionDone:
		case <-time.After(2 * time.Second):
			fmt.Printf("Vision: WARNING - shutdown timeout\n")
		}
	}()
	var recorder voice.Recorder
	var piper *voice.Piper
	var pcmPlayer voice.PCMPlayer
	var transcriber voice.Groq
	if *voiceMode {
		recorder, err = voice.NewRecorderWithMode(os.Getenv("ARECORD_COMMAND"), os.Getenv("AUDIO_INPUT_DEVICE"), envString("STT_PREPROCESSOR", "raw"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "Status: CRITICAL - STT preprocessor: %s\n", err)
			return 1
		}
		defer recorder.Close()
		transcriber = voice.NewGroq(os.Getenv("GROQ_API_KEY"), os.Getenv("STT_MODEL"), os.Getenv("STT_LANGUAGE"), "", httpClient)
		transcriber.OnTrace = func(metrics voice.HTTPTraceMetrics) {
			if *debug {
				fmt.Printf("[NETWORK GROQ]\ndns_ms=%.1f\nconnect_ms=%.1f\ntls_ms=%.1f\nconnection_reused=%t\nttfb_ms=%.1f\nbody_ms=%.1f\ntotal_ms=%.1f\n", ms(metrics.DNS), ms(metrics.Connect), ms(metrics.TLS), metrics.Reused, ms(metrics.TTFB), ms(metrics.Body), ms(metrics.Total))
			}
		}
		piper, err = voice.NewPiper(os.Getenv("PIPER_COMMAND"), os.Getenv("PIPER_SCRIPT"), os.Getenv("PIPER_MODEL"))
		if err != nil {
			fmt.Fprintf(os.Stderr, "Status: CRITICAL - Piper: %s\n", err)
			return 1
		}
		audioCommand := envString("PIPER_AUDIO_COMMAND", "aplay")
		if _, err := exec.LookPath(audioCommand); err != nil {
			fmt.Fprintf(os.Stderr, "SIRAH: speech output requires %q; install it or set PIPER_AUDIO_COMMAND: %s\n", audioCommand, err)
			return 1
		}
		if err := piper.Start(runCtx); err != nil {
			fmt.Fprintf(os.Stderr, "Status: CRITICAL - Piper: %s\n", err)
			return 1
		}
		defer piper.Close()
		pcmPlayer = voice.NewPCMPlayer(audioCommand, os.Getenv("PIPER_AUDIO_DEVICE"), piper.SampleRate())
		defer pcmPlayer.Close()
	}
	body := startBodyController(runCtx, mot, bodyControllerConfig{
		NaturalBlink: envBool("NATURAL_BLINK_ENABLED", true) && device == serialDevice,
		OnResult: func(action sirah.Action, natural bool, err error, duration time.Duration) {
			if err != nil {
				fmt.Printf("Status: WARNING - motion %s: %s\n", action, err)
			}
			if *debug {
				source := "explicit"
				if natural {
					source = "natural"
				}
				result := "sent"
				if err != nil {
					result = "error"
				}
				fmt.Printf("[MOTION]\naction=%s\nsource=%s\nresult=%s\nlatency_ms=%.1f\n", action, source, result, ms(duration))
			}
		},
	})
	defer func() {
		stop()
		if serialDevice != nil {
			_ = serialDevice.Close()
		}
		body.Wait()
	}()

	turn := func(ctx context.Context, text string, vadDuration, sttDuration time.Duration) {
		if !*voiceMode {
			response, err := robot.RespondWithContextStream(ctx, text, sirah.Context{Perception: perception.Load(), PerceptionMaxAge: 2 * time.Second}, func(string) error { return nil })
			if err != nil {
				fmt.Fprintf(os.Stderr, "SIRAH: conversation failed: %s\n", err)
				exitCode = 1
				return
			}
			// Terminal output uses the same marker cleanup, without scheduling
			// physical actions against a nonexistent PCM playback timeline.
			fmt.Printf("Robot: %s\n", sirah.CleanTimeline(sirah.ParseTimeline(response.Speech)))
			_ = robot.RecordTurn(ctx, text, response)
			return
		}
		started := time.Now()
		// Timeline intercalada: TEXT -> TTS, ACTION -> Motion/Serial en orden.
		// La posicion se mide en bytes PCM realmente escritos al altavoz
		// (accountAudio), sin sleeps de sincronizacion. El tracking de Vision
		// corre en su propia goroutine y nunca se bloquea aqui.
		var enqueuedBytes atomic.Int64
		var writtenBytes atomic.Int64
		writeNotify := make(chan struct{}, 1)
		speakerWritesShown := 0
		accountAudio := func(event string, at time.Time, size int) {
			if event == "speaker_write_done" {
				writtenBytes.Add(int64(size))
				select {
				case writeNotify <- struct{}{}:
				default:
				}
			}
		}
		countEnqueued := func(trace func(string, time.Time, int)) func(string, time.Time, int) {
			return func(event string, at time.Time, size int) {
				if event == "pcm_enqueue" {
					enqueuedBytes.Add(int64(size))
				}
				if trace != nil {
					trace(event, at, size)
				}
			}
		}
		llmDuration = 0
		contextTiming = sirah.ContextTiming{}
		llmMetadata = sirah.LLMResponseMetadata{}
		streamTelemetry = sirah.LLMStreamTelemetry{}
		ollamaTrace = sirah.HTTPTraceMetrics{}
		snapshot := perception.Load()
		runtimeContext := sirah.Context{Perception: snapshot, PerceptionMaxAge: 2 * time.Second}
		turnAvailableActions := append([]sirah.Action(nil), robot.AvailableActions...)
		if runtimeContext.HardwareStatus != (sirah.HardwareStatus{}) {
			turnAvailableActions = sirah.FilterActions(turnAvailableActions, runtimeContext.HardwareStatus)
		}
		actionScheduler := &sirah.ActionScheduler{
			Act: newTurnActionEnqueuer(turnAvailableActions, body.Enqueue),
			OnError: func(action sirah.Action, err error) {
				fmt.Printf("Status: WARNING - motion %s: %s\n", action, err)
			},
		}
		stopMonitor := startActionMonitor(ctx, actionScheduler, writeNotify, &writtenBytes)
		defer stopMonitor()
		if *debug {
			logPerception(snapshot)
		}
		var response sirah.Response
		var err error
		streamed := false
		var stableSpeechChunk time.Time
		if _, ok := robot.LLM.(sirah.StreamingLLM); ok {
			streamed = true
			streamCtx, streamCancel := context.WithCancel(ctx)
			defer streamCancel()
			itemQueue := make(chan speechItem, 32)
			timelineFilter := sirah.NewTimelineFilter()
			feedItem := func(item speechItem) error {
				select {
				case itemQueue <- item:
					return nil
				case <-streamCtx.Done():
					return streamCtx.Err()
				}
			}
			feedTimelineEvents := func(events []sirah.TimelineEvent) error {
				for _, event := range events {
					if event.Kind == sirah.TimelineAction {
						if err := feedItem(speechItem{isAction: true, action: event.Action}); err != nil {
							return err
						}
						continue
					}
					// Whitespace-only text is preserved: the chunker keeps it
					// for later chunks and never emits blank text to Piper.
					if err := feedItem(speechItem{text: event.Text}); err != nil {
						return err
					}
				}
				return nil
			}
			audioQueue := make(chan []byte, 8)
			pipelineDone := make(chan error, 1)
			firstContent, firstSpeech, firstPiperPCM, firstAudioWrite := time.Time{}, time.Time{}, time.Time{}, time.Time{}
			var streamMu sync.Mutex
			pcmTrace := func(event string, at time.Time, size int) {
				// Per-write events flood the log (dozens per turn); show the
				// first pair and count the rest into the turn summary.
				if event == "speaker_write_start" || event == "speaker_write_done" {
					if speakerWritesShown >= 2 {
						return
					}
					speakerWritesShown++
				}
				if *debug {
					fmt.Printf("[PCM]\nevent=%s\nturn_ms=%.1f\nbytes=%d\n", event, ms(at.Sub(started)), size)
				}
			}
			pcmPlayer.OnEvent = func(event string, at time.Time, size int) {
				accountAudio(event, at, size)
				pcmTrace(event, at, size)
			}
			pcmPlayer.OnFirstWrite = func(_ time.Duration) {
				streamMu.Lock()
				if firstAudioWrite.IsZero() {
					firstAudioWrite = time.Now()
				}
				contentAt, speechAt, piperAt, audioAt := firstContent, firstSpeech, firstPiperPCM, firstAudioWrite
				streamMu.Unlock()
				if contentAt.IsZero() {
					return
				}
				if *debug {
					fmt.Printf("[STREAM]\nuser_end_to_llm_first_content_ms=%.1f\nfirst_speech_chunk_ms=%.1f\npiper_first_pcm_ms=%.1f\nfirst_audio_write_ms=%.1f\n", ms(contentAt.Sub(started)), ms(speechAt.Sub(started)), ms(piperAt.Sub(started)), ms(audioAt.Sub(started)))
				}
			}
			go func() {
				pipelineDone <- streamPiperSpeech(streamCtx, piper, &pcmPlayer, itemQueue, audioQueue, envDuration("PIPER_PREBUFFER_MS", 80*time.Millisecond), func() {
					streamMu.Lock()
					if firstSpeech.IsZero() {
						firstSpeech = time.Now()
						stableSpeechChunk = firstSpeech
					}
					streamMu.Unlock()
				}, func() {
					streamMu.Lock()
					if firstPiperPCM.IsZero() {
						firstPiperPCM = time.Now()
					}
					streamMu.Unlock()
				}, countEnqueued(pcmTrace), func(action sirah.Action) {
					actionScheduler.Schedule(enqueuedBytes.Load(), action)
					actionScheduler.MaybeFire(streamCtx, writtenBytes.Load())
				})
			}()
			response, err = robot.RespondWithContextStream(streamCtx, text, runtimeContext, func(fragment string) error {
				streamMu.Lock()
				if firstContent.IsZero() {
					firstContent = time.Now()
				}
				streamMu.Unlock()
				return feedTimelineEvents(timelineFilter.Push(fragment))
			})
			if err != nil {
				streamCancel()
			}
			if flushErr := feedTimelineEvents(timelineFilter.Flush()); err == nil {
				err = flushErr
			}
			close(itemQueue)
			if pipelineErr := <-pipelineDone; err == nil {
				err = pipelineErr
			}
			actionScheduler.MaybeFire(streamCtx, writtenBytes.Load())
		} else {
			response, err = robot.RespondWithContext(ctx, text, runtimeContext)
		}
		if err != nil {
			fmt.Printf("Status: CRITICAL - agent: %s\n", err)
			exitCode = 1
			return
		}
		if err := sirah.ValidateResponse(response); err != nil {
			fmt.Printf("Status: CRITICAL - invalid response: %s\n", err)
			exitCode = 1
			return
		}
		rawSpeech := response.Speech
		timeline := sirah.AppendLegacyActions(sirah.ParseTimeline(rawSpeech), response.Actions)
		cleaned := sirah.CleanTimeline(timeline)
		response.Speech = cleaned
		if *debug {
			streamTelemetry.FirstStableSpeechChunk = stableSpeechChunk
			fmt.Printf("[LLM_STREAM]\nrequest_start_ms=%s\nheaders_received_ms=%s\nfirst_sse_event_ms=%s\nfirst_reasoning_event_ms=%s\nfirst_content_event_ms=%s\nfirst_speech_character_ms=%s\nfirst_stable_speech_chunk_ms=%s\nstream_complete_ms=%s\nconnection_reused=%t\nreasoning_present=%t\nreasoning_first_ms=%s\nreasoning_duration_before_content_ms=%s\nreasoning_chars=%d\nreasoning_tokens=%s\n", relativeMetric(started, streamTelemetry.RequestStart), relativeMetric(started, streamTelemetry.HeadersReceived), relativeMetric(started, streamTelemetry.FirstSSEEvent), relativeMetric(started, streamTelemetry.FirstReasoningEvent), relativeMetric(started, streamTelemetry.FirstContentEvent), relativeMetric(started, streamTelemetry.FirstSpeechCharacter), relativeMetric(started, streamTelemetry.FirstStableSpeechChunk), relativeMetric(started, streamTelemetry.StreamComplete), streamTelemetry.ConnectionReused, streamTelemetry.ReasoningPresent, relativeMetric(started, streamTelemetry.FirstReasoningEvent), metricDelta(streamTelemetry.FirstReasoningEvent, streamTelemetry.FirstContentEvent), streamTelemetry.ReasoningChars, nullableInt(streamTelemetry.ReasoningTokens))
			fmt.Printf("[LLM]\nprovider=%s\nmodel=%s\ncontext_build_ms=%.1f\nrecent_ms=%.1f\nrecall_ms=%.1f\nprompt_bytes=%d\ninput_tokens=%d\noutput_tokens=%d\nllm_ttfb_ms=%.1f\nllm_total_ms=%.1f\n", llmProviderName(), envString("LLM_MODEL", ""), ms(contextTiming.Total), ms(contextTiming.Recent), ms(contextTiming.Recall), llmMetadata.PromptBytes, llmMetadata.InputTokens, llmMetadata.OutputTokens, ms(ollamaTrace.TTFB), ms(llmDuration))
			fmt.Printf("[RESPONSE]\nspeech=%q\nactions=%v\ntimeline=%v\n", response.Speech, response.Actions, timelineActionNames(timeline))
		}
		_ = robot.RecordTurn(ctx, text, response)
		if !streamed && len(timeline) > 0 {
			ttsStarted := time.Now()
			pcmPlayer.OnEvent = accountAudio
			pcmPlayer.OnFirstWrite = func(duration time.Duration) {
				if *debug {
					fmt.Printf("[SPEAKER]\nfirst_pcm_write_ms=%.1f\n", ms(duration))
				}
			}
			itemQueue := make(chan speechItem, 32)
			audioQueue := make(chan []byte, 8)
			playDone := make(chan error, 1)
			go func() {
				playDone <- streamPiperSpeech(ctx, piper, &pcmPlayer, itemQueue, audioQueue, envDuration("PIPER_PREBUFFER_MS", 80*time.Millisecond), nil, nil, countEnqueued(nil), func(action sirah.Action) {
					actionScheduler.Schedule(enqueuedBytes.Load(), action)
					actionScheduler.MaybeFire(ctx, writtenBytes.Load())
				})
			}()
		feedLoop:
			for _, event := range timeline {
				item := speechItem{text: event.Text}
				if event.Kind == sirah.TimelineAction {
					item = speechItem{isAction: true, action: event.Action}
				} else if event.Text == "" {
					continue
				}
				select {
				case itemQueue <- item:
				case <-ctx.Done():
					break feedLoop
				}
			}
			close(itemQueue)
			if err := <-playDone; err != nil {
				fmt.Printf("Status: CRITICAL - TTS/Speaker: %s\n", err)
				exitCode = 1
				return
			}
			actionScheduler.MaybeFire(ctx, writtenBytes.Load())
			ttsDuration := time.Since(ttsStarted)
			if *debug {
				fmt.Printf("[TTS]\npiper_complete_ms=%.1f\n", ms(ttsDuration))
			}
		} else if streamed {
			// Inline markers already fired during streaming. Only legacy
			// response.Actions without an inline representation remain.
			for _, action := range sirah.FinalStreamActions(rawSpeech, response.Actions) {
				actionScheduler.Schedule(enqueuedBytes.Load(), action)
			}
			actionScheduler.MaybeFire(ctx, writtenBytes.Load())
		}
		if err == nil {
			fmt.Printf("Robot: %s\n", cleaned)
		}
		if *debug {
			fmt.Printf("[TOTAL]\nturn_ms=%.1f\n", ms(time.Since(started)))
		}
	}

	interact := func() {
		if *voiceMode {
			wakeText := configuredWakeupText()
			if wakeText != "" {
				if envBool("CREATIVE_WAKEUP_ENABLED", false) {
					generationStarted := time.Now()
					generated, generationErr := generateCreativeWakeup(runCtx, robot, generationStarted)
					source := "fallback"
					if generationErr != nil {
						fmt.Printf("Status: WARNING - creative wake-up: %s; using configured fallback\n", generationErr)
					} else {
						wakeText = generated
						source = "llm"
					}
					if *debug {
						fmt.Printf("[WAKEUP]\nsource=%s\ngeneration_ms=%.1f\n", source, ms(time.Since(generationStarted)))
					}
				}
				wakeStarted := time.Now()
				err := runWakeup(runCtx, wakeText, body, func(ctx context.Context, text string, firstPCMWrite func()) error {
					return speakWakeup(ctx, piper, &pcmPlayer, text, envDuration("PIPER_PREBUFFER_MS", 80*time.Millisecond), *debug, firstPCMWrite)
				})
				if err != nil {
					fmt.Printf("Status: WARNING - wake-up: %s\n", err)
				} else {
					fmt.Printf("Robot: %s\n", wakeText)
				}
				if *debug {
					fmt.Printf("[WAKEUP]\ntotal_ms=%.1f\n", ms(time.Since(wakeStarted)))
				}
				if snapshot := perception.Load(); snapshot != nil && snapshot.FaceVisible && time.Since(snapshot.UpdatedAt) <= 2*time.Second {
					if err := body.Enqueue(sirah.ActionLookAtUser); err != nil {
						fmt.Printf("Status: WARNING - wake-up tracking: %s\n", err)
					}
				}
			}
			body.EnableNaturalBlink()
			runVoice(runCtx, turn, recorder, transcriber, *debug)
			return
		}
		body.EnableNaturalBlink()
		fmt.Println("S.I.R.A.H.\nSistema Inteligente Robótico de Asistencia Humana\n\nText mode — type one message per line and press Enter.\nCtrl+C or Ctrl+D to exit.")
		fmt.Print("> ")
		reader := bufio.NewScanner(os.Stdin)
		lines := make(chan string)
		readErrors := make(chan error, 1)
		go func() {
			defer close(lines)
			for reader.Scan() {
				select {
				case lines <- strings.TrimSpace(reader.Text()):
				case <-runCtx.Done():
					readErrors <- nil
					return
				}
			}
			readErrors <- reader.Err()
		}()
		for {
			select {
			case <-runCtx.Done():
				return
			case text, ok := <-lines:
				if !ok {
					if err := <-readErrors; err != nil {
						fmt.Fprintf(os.Stderr, "SIRAH: reading stdin: %s\n", err)
						exitCode = 1
					}
					return
				}
				if text != "" {
					turn(runCtx, text, 0, 0)
				}
				fmt.Print("> ")
			}
		}
	}
	if *preview && visionEnabled {
		// OpenCV highgui pumps its window on the calling thread: vision
		// owns the main thread here and interaction runs behind it.
		interactionDone := make(chan struct{})
		go func() {
			defer close(interactionDone)
			defer stop()
			interact()
		}()
		runtime.LockOSThread()
		defer runtime.UnlockOSThread()
		visionStarted = true
		runVision()
		stop()
		<-interactionDone
		return exitCode
	}
	visionStarted = true
	go runVision()
	interact()
	return exitCode
}

func configuredWakeupText() string {
	if value, ok := os.LookupEnv("WAKEUP_TEXT"); ok {
		return strings.TrimSpace(value)
	}
	return defaultWakeupText
}

func speakWakeup(ctx context.Context, piper *voice.Piper, player *voice.PCMPlayer, text string, prebuffer time.Duration, debug bool, firstPCMWrite func()) error {
	items := make(chan speechItem, 1)
	audio := make(chan []byte, 8)
	items <- speechItem{text: text}
	close(items)
	started := time.Now()
	player.OnEvent = nil
	player.OnFirstWrite = func(duration time.Duration) {
		if firstPCMWrite != nil {
			firstPCMWrite()
		}
		if debug {
			fmt.Printf("[WAKEUP]\nfirst_audio_write_ms=%.1f\n", ms(duration))
		}
	}
	return streamPiperSpeech(ctx, piper, player, items, audio, prebuffer, nil, func() {
		if debug {
			fmt.Printf("[WAKEUP]\npiper_first_pcm_ms=%.1f\n", ms(time.Since(started)))
		}
	}, nil, nil)
}

// speechItem conserva el orden del LLM: el texto fluye a TTS y la accion a
// Motion/Serial. La accion se agenda cuando todo el audio previo ya se
// encolo, y se dispara cuando ese audio ya sono (ActionScheduler).
type speechItem struct {
	text     string
	action   sirah.Action
	isAction bool
}

func newTurnActionEnqueuer(available []sirah.Action, enqueue func(sirah.Action) error) func(sirah.Action) error {
	allowed := make(map[sirah.Action]struct{}, len(available))
	for _, action := range available {
		allowed[action] = struct{}{}
	}
	return func(action sirah.Action) error {
		if _, ok := allowed[action]; !ok {
			// A rejected action is a no-op so speech and later valid actions continue.
			return nil
		}
		return enqueue(action)
	}
}

// startActionMonitor dispara las acciones pendientes a medida que el
// reproductor confirma bytes, sin bloquear la alimentacion de audio y sin
// temporizadores. Devuelve la funcion de parada (hace un ultimo flush).
func startActionMonitor(ctx context.Context, scheduler *sirah.ActionScheduler, notify <-chan struct{}, written *atomic.Int64) func() {
	monitorCtx, stop := context.WithCancel(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			select {
			case <-monitorCtx.Done():
				scheduler.MaybeFire(context.Background(), written.Load())
				return
			case <-notify:
				scheduler.MaybeFire(monitorCtx, written.Load())
			}
		}
	}()
	return func() {
		stop()
		<-done
	}
}

func timelineActionNames(timeline []sirah.TimelineEvent) []string {
	var names []string
	for _, event := range timeline {
		if event.Kind == sirah.TimelineAction {
			names = append(names, string(event.Action))
		}
	}
	return names
}

func streamPiperSpeech(ctx context.Context, piper *voice.Piper, player *voice.PCMPlayer, items <-chan speechItem, audio chan []byte, prebuffer time.Duration, onFirstSpeech, onFirstPCM func(), trace func(string, time.Time, int), onAction func(sirah.Action)) error {
	playDone := make(chan error, 1)
	go func() { playDone <- player.Play(ctx, audio, prebuffer) }()
	chunker := sirah.NewSpeechChunker()
	flush := time.NewTicker(120 * time.Millisecond)
	defer flush.Stop()
	synthesize := func(chunks []string) error {
		for _, text := range chunks {
			if onFirstSpeech != nil {
				onFirstSpeech()
			}
			if err := piper.SynthesizeStream(ctx, text, func(chunk []byte) error {
				if onFirstPCM != nil {
					onFirstPCM()
				}
				if trace != nil {
					trace("pcm_chunk_created", time.Now(), len(chunk))
				}
				copyChunk := append([]byte(nil), chunk...)
				select {
				case audio <- copyChunk:
					if trace != nil {
						trace("pcm_enqueue", time.Now(), len(copyChunk))
					}
					return nil
				case <-ctx.Done():
					return ctx.Err()
				}
			}); err != nil {
				return err
			}
		}
		return nil
	}
	flushAction := func(action sirah.Action) error {
		if err := synthesize(chunker.Flush()); err != nil {
			return err
		}
		if onAction != nil {
			onAction(action)
		}
		return nil
	}
	for {
		select {
		case item, ok := <-items:
			if !ok {
				err := synthesize(chunker.Flush())
				close(audio)
				if playErr := <-playDone; err == nil {
					err = playErr
				}
				return err
			}
			if item.isAction {
				if err := flushAction(item.action); err != nil {
					close(audio)
					<-playDone
					return err
				}
				continue
			}
			if err := synthesize(chunker.Push(item.text)); err != nil {
				close(audio)
				<-playDone
				return err
			}
		case <-flush.C:
			if err := synthesize(chunker.FlushStable()); err != nil {
				close(audio)
				<-playDone
				return err
			}
		case <-ctx.Done():
			close(audio)
			<-playDone
			return ctx.Err()
		}
	}
}

func runVisionTargets(ctx context.Context, updates <-chan vision.Target, mot *motion.Motion, debug bool) {
	lastDebug := time.Time{}
	for {
		select {
		case <-ctx.Done():
			return
		case target := <-updates:
			err := mot.UpdateTarget(motion.Target{X: target.X, Y: target.Y})
			requested, _, _, delivery, _ := mot.Snapshot()
			if debug && (lastDebug.IsZero() || time.Since(lastDebug) >= 350*time.Millisecond) {
				fmt.Printf("TARGET vision: x=%.3f y=%.3f\n", target.X, target.Y)
				if requested == motion.TrackingIdle {
					fmt.Printf("TARGET sent: suppressed mode=%s\n", requested)
				} else {
					fmt.Printf("TARGET sent: x=%.3f y=%.3f mode=%s delivery=%s\n", target.X, target.Y, requested, delivery)
				}
				lastDebug = time.Now()
			}
			if err != nil && err != firmware.ErrUnavailable {
				fmt.Printf("Vision: WARNING - target: %s\n", err)
			}
		}
	}
}

func runFirmwareEvents(ctx context.Context, events <-chan firmware.Event, mot *motion.Motion) {
	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-events:
			if !ok {
				return
			}
			mot.HandleHardwareEvent(event)
		}
	}
}

func formatTarget(target *vision.Target) string {
	if target == nil {
		return "none"
	}
	return fmt.Sprintf("(%.3f,%.3f)", target.X, target.Y)
}

func runVoice(parent context.Context, turn func(context.Context, string, time.Duration, time.Duration), recorder voice.Recorder, transcriber voice.Transcriber, debug bool) {
	ctx, stop := signal.NotifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()
	config := voice.VADConfigFromEnv(os.Getenv)
	config.Debug = debug
	config.OnCalibration = func(stats voice.CalibrationStats) {
		if debug {
			fmt.Printf("[VAD CALIBRATION]\nrms_min=%.1f\nrms_median=%.1f\nrms_p90=%.1f\nrms_p99=%.1f\nrms_max=%.1f\n", stats.Min, stats.Median, stats.P90, stats.P99, stats.Max)
		}
	}
	fmt.Println("Voice mode: manos libres")
	for ctx.Err() == nil {
		var vadResult voice.VADResult
		config.OnResult = func(result voice.VADResult) { vadResult = result }
		vadStarted := time.Now()
		audio, _, err := recorder.RecordUtterance(ctx, config)
		vadDuration := time.Since(vadStarted)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			fmt.Printf("Voice: WARNING - %s\n", err)
			continue
		}
		sttStarted := time.Now()
		sttCtx, cancel := context.WithTimeout(ctx, envDuration("STT_TIMEOUT", 30*time.Second))
		rawText, err := transcriber.Transcribe(sttCtx, audio)
		sttDuration := time.Since(sttStarted)
		sttDone := sttStarted.Add(sttDuration)
		cancel()
		if err != nil {
			fmt.Printf("Status: WARNING - STT: %s\n", err)
			continue
		}
		text := voice.CleanTranscript(rawText)
		if debug {
			fmt.Printf("[VOICE]\nraw_transcript=%q\nclean_transcript=%q\ncapture_rate_hz=%d\ncapture_start_ms=0.0\nfirst_speech_ms=%.1f\nuser_end_estimated_ms=%.1f\nutterance_closed_ms=%.1f\nendpoint_delay_ms=%.1f\nstt_start_ms=%.1f\nstt_done_ms=%.1f\nvad_ms=%.1f\nstt_ms=%.1f\nutterance_ms=%.1f\nwait_for_speech_ms=%.1f\nspeech_duration_ms=%.1f\nend_silence_ms=%.1f\nend_reason=%s\n", rawText, text, vadResult.SampleRate, relativeMS(vadResult.CaptureStart, vadResult.FirstSpeech), relativeMS(vadResult.CaptureStart, vadResult.UserEnd), relativeMS(vadResult.CaptureStart, vadResult.ClosedAt), ms(vadResult.ClosedAt.Sub(vadResult.UserEnd)), relativeMS(vadResult.CaptureStart, sttStarted), relativeMS(vadResult.CaptureStart, sttDone), ms(vadDuration), ms(sttDuration), ms(vadResult.TotalDuration), ms(vadResult.WaitForSpeech), ms(vadResult.SpeechDuration), ms(vadResult.EndSilence), vadResult.EndReason)
		}
		if text == "" {
			fmt.Println("Status: WARNING - STT returned empty transcript")
			continue
		}
		turn(ctx, text, vadDuration, sttDuration)
		cooldown := envDuration("VOICE_COOLDOWN_MS", config.Cooldown)
		if cooldown > 0 {
			timer := time.NewTimer(cooldown)
			select {
			case <-timer.C:
			case <-ctx.Done():
				if !timer.Stop() {
					<-timer.C
				}
				return
			}
		}
	}
}

func relativeMS(start, value time.Time) float64 {
	if start.IsZero() || value.IsZero() {
		return 0
	}
	return ms(value.Sub(start))
}

func relativeMetric(start, value time.Time) string {
	if start.IsZero() || value.IsZero() {
		return "null"
	}
	return fmt.Sprintf("%.1f", ms(value.Sub(start)))
}

func metricDelta(start, end time.Time) string {
	if start.IsZero() || end.IsZero() {
		return "null"
	}
	return fmt.Sprintf("%.1f", ms(end.Sub(start)))
}

func nullableInt(value *int) string {
	if value == nil {
		return "null"
	}
	return fmt.Sprint(*value)
}

// llmProviderName avoids hardcoding a provider label in diagnostics: explicit
// LLM_PROVIDER wins, otherwise the host of LLM_BASE_URL is used.
func llmProviderName() string {
	if name := strings.TrimSpace(os.Getenv("LLM_PROVIDER")); name != "" {
		return name
	}
	parsed, err := url.Parse(strings.TrimSpace(os.Getenv("LLM_BASE_URL")))
	if err != nil || parsed.Host == "" {
		return "unknown"
	}
	return parsed.Host
}

func providerRequestHeaders(baseURL, sessionID string) map[string]string {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Hostname() != "opencode.ai" || !strings.HasPrefix(strings.TrimRight(parsed.Path, "/"), "/zen/go/v1") {
		return nil
	}
	return map[string]string{
		"User-Agent":         "sirah/0.1",
		"X-Opencode-Session": sessionID,
	}
}

func logPerception(snapshot *vision.PerceptionSnapshot) {
	if snapshot == nil {
		fmt.Println("[PERCEPTION]\nface_visible=false\nperson_visible=false\nface_count=0\nfresh=false\nage_ms=0")
		return
	}
	age := time.Since(snapshot.UpdatedAt)
	fresh := !snapshot.UpdatedAt.IsZero() && age >= 0 && age <= 2*time.Second
	if !fresh {
		fmt.Printf("[PERCEPTION]\nface_visible=false\nperson_visible=false\nface_count=0\nfresh=false\nage_ms=%d\n", maxInt64(0, age.Milliseconds()))
		return
	}
	fmt.Printf("[PERCEPTION]\nface_visible=%t\nperson_visible=%t\nface_count=%d\nfresh=true\nage_ms=%d\n", snapshot.FaceVisible, snapshot.PersonVisible, snapshot.FaceCount, age.Milliseconds())
}

func maxInt64(value, minimum int64) int64 {
	if value < minimum {
		return minimum
	}
	return value
}

func ms(value time.Duration) float64 { return float64(value.Microseconds()) / 1000 }

func openSerial(path string, baud int) *os.File {
	if strings.TrimSpace(path) == "" {
		return nil
	}
	if baud <= 0 {
		baud = 115200
	}
	file, err := os.OpenFile(path, os.O_RDWR, 0)
	if err != nil {
		fmt.Printf("Firmware: WARNING - %s\n", err)
		return nil
	}
	// os.OpenFile cannot set baud rate; configure 8N1 raw via stty so the
	// ESP32 (115200) and Go agree. Failure degrades to no hardware.
	sttyCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := exec.CommandContext(sttyCtx, "stty", "-F", path, strconv.Itoa(baud), "raw", "-echo").Run(); err != nil {
		fmt.Printf("Firmware: WARNING - stty %s %d: %s\n", path, baud, err)
		_ = file.Close()
		return nil
	}
	return file
}

// handshakeFirmware verifies the link without moving anything. STATUS is
// answered with bare READY even when the board did not reboot on open, so it
// is sent first and then READY is awaited (with one retry covering the
// open-during-boot race). Any failure only degrades eyes; conversation
// continues.
func handshakeFirmware(ctx context.Context, serialDevice *firmware.Serial) error {
	for attempt := 0; attempt < 2; attempt++ {
		if err := serialDevice.Send(firmware.Command{Type: firmware.CommandStatus}); err != nil {
			return fmt.Errorf("STATUS send: %w", err)
		}
		readyCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		err := serialDevice.WaitReady(readyCtx)
		cancel()
		if err == nil {
			status, err := serialDevice.SendWithStatus(firmware.Command{Type: firmware.CommandStatus})
			if err != nil {
				return fmt.Errorf("STATUS: %w", err)
			}
			fmt.Printf("Firmware: READY (delivery=%s)\n", status)
			return nil
		}
		if ctx.Err() != nil {
			return fmt.Errorf("no READY: %w", err)
		}
	}
	return fmt.Errorf("no READY after STATUS retries")
}

func loadDotEnv(path string) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		line = strings.TrimPrefix(line, "export ")
		key, value, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		key, value = strings.TrimSpace(key), strings.Trim(strings.TrimSpace(value), "\"")
		if key != "" && os.Getenv(key) == "" {
			os.Setenv(key, value)
		}
	}
}

func envString(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}
func envInt(name string, fallback int) int {
	var value int
	if _, err := fmt.Sscanf(os.Getenv(name), "%d", &value); err == nil && value > 0 {
		return value
	}
	return fallback
}

func visionShouldStart(preview bool) bool {
	return preview || envBool("VISION_ENABLED", false)
}

func envBool(name string, fallback bool) bool {
	value := strings.TrimSpace(strings.ToLower(os.Getenv(name)))
	if value == "" {
		return fallback
	}
	return value == "1" || value == "true" || value == "yes" || value == "on"
}
func envDuration(name string, fallback time.Duration) time.Duration {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		if parsed, err := time.ParseDuration(value); err == nil {
			return parsed
		}
		if number := envInt(name, 0); number > 0 {
			return time.Duration(number) * time.Millisecond
		}
	}
	return fallback
}
