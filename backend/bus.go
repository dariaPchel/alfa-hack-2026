package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/segmentio/kafka-go"
)

type AnalysisRequested struct {
	AnalysisID string `json:"analysis_id"`
	CompanyID  string `json:"company_id"`
	EventID    string `json:"event_id"`
	Question   string `json:"question"`
}

type Bus struct {
	brokers         []string
	requestTopic    string
	completedTopic  string
	deadTopic       string
	requestWriter   *kafka.Writer
	completedWriter *kafka.Writer
	deadWriter      *kafka.Writer
}

func NewBus() *Bus {
	brokers := splitCSV(os.Getenv("KAFKA_BROKERS"))
	if len(brokers) == 0 {
		return nil
	}
	requestTopic := envString("KAFKA_REQUEST_TOPIC", "analysis.requested")
	completedTopic := envString("KAFKA_COMPLETED_TOPIC", "analysis.completed")
	deadTopic := envString("KAFKA_DEAD_TOPIC", "analysis.failed")
	return &Bus{
		brokers:         brokers,
		requestTopic:    requestTopic,
		completedTopic:  completedTopic,
		deadTopic:       deadTopic,
		requestWriter:   &kafka.Writer{Addr: kafka.TCP(brokers...), Topic: requestTopic, Balancer: &kafka.Hash{}},
		completedWriter: &kafka.Writer{Addr: kafka.TCP(brokers...), Topic: completedTopic, Balancer: &kafka.Hash{}},
		deadWriter:      &kafka.Writer{Addr: kafka.TCP(brokers...), Topic: deadTopic, Balancer: &kafka.Hash{}},
	}
}

func (b *Bus) PublishRequested(ctx context.Context, request AnalysisRequested) error {
	return b.publish(ctx, b.requestWriter, request.AnalysisID, request)
}

func (b *Bus) PublishCompleted(ctx context.Context, analysis Analysis) error {
	return b.publish(ctx, b.completedWriter, analysis.ID, analysis)
}

func (b *Bus) publish(ctx context.Context, writer *kafka.Writer, key string, value any) error {
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return writer.WriteMessages(ctx, kafka.Message{Key: []byte(key), Value: payload})
}

func (b *Bus) RunWorker(ctx context.Context, process func(context.Context, AnalysisRequested) error,
	markFailed func(context.Context, string, error) error) error {
	if b == nil {
		return fmt.Errorf("kafka bus is not configured")
	}
	if err := b.ensureTopics(ctx); err != nil {
		return fmt.Errorf("prepare Kafka topics: %w", err)
	}
	reader := kafka.NewReader(kafka.ReaderConfig{
		Brokers:               b.brokers,
		Topic:                 b.requestTopic,
		GroupID:               envString("KAFKA_CONSUMER_GROUP", "alfa-analysis-worker"),
		MinBytes:              1,
		MaxBytes:              10e6,
		WatchPartitionChanges: true,
	})
	defer reader.Close()
	for {
		message, err := reader.FetchMessage(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			log.Printf("Kafka fetch failed: %v", err)
			time.Sleep(2 * time.Second)
			continue
		}
		var request AnalysisRequested
		if err := json.Unmarshal(message.Value, &request); err != nil || request.AnalysisID == "" {
			failure := map[string]any{"error": "invalid analysis request", "raw": string(message.Value)}
			if publishErr := b.publish(ctx, b.deadWriter, string(message.Key), failure); publishErr != nil {
				return publishErr
			}
		} else {
			var processErr error
			for attempt := 1; attempt <= 3; attempt++ {
				processErr = process(ctx, request)
				if processErr == nil {
					break
				}
				log.Printf("analysis %s attempt %d failed: %v", request.AnalysisID, attempt, processErr)
				if attempt < 3 {
					select {
					case <-ctx.Done():
						return ctx.Err()
					case <-time.After(time.Duration(attempt*attempt) * time.Second):
					}
				}
			}
			if processErr != nil {
				if err := markFailed(ctx, request.AnalysisID, processErr); err != nil {
					return err
				}
				failure := map[string]any{"analysis_id": request.AnalysisID, "error": processErr.Error(), "attempts": 3}
				if err := b.publish(ctx, b.deadWriter, request.AnalysisID, failure); err != nil {
					return err
				}
			}
		}
		if err := reader.CommitMessages(ctx, message); err != nil {
			return err
		}
	}
}

func (b *Bus) ensureTopics(ctx context.Context) error {
	broker, err := kafka.DialContext(ctx, "tcp", b.brokers[0])
	if err != nil {
		return err
	}
	controller, err := broker.Controller()
	_ = broker.Close()
	if err != nil {
		return err
	}
	address := fmt.Sprintf("%s:%d", controller.Host, controller.Port)
	conn, err := kafka.DialContext(ctx, "tcp", address)
	if err != nil {
		return err
	}
	defer conn.Close()
	return conn.CreateTopics(
		kafka.TopicConfig{Topic: b.requestTopic, NumPartitions: 1, ReplicationFactor: 1},
		kafka.TopicConfig{Topic: b.completedTopic, NumPartitions: 1, ReplicationFactor: 1},
		kafka.TopicConfig{Topic: b.deadTopic, NumPartitions: 1, ReplicationFactor: 1},
	)
}

func (b *Bus) Close() error {
	if b == nil {
		return nil
	}
	var first error
	if err := b.requestWriter.Close(); err != nil {
		first = err
	}
	if err := b.completedWriter.Close(); err != nil && first == nil {
		first = err
	}
	if err := b.deadWriter.Close(); err != nil && first == nil {
		first = err
	}
	return first
}

func splitCSV(value string) []string {
	var result []string
	for _, item := range strings.Split(value, ",") {
		if item = strings.TrimSpace(item); item != "" {
			result = append(result, item)
		}
	}
	return result
}

func envString(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}
