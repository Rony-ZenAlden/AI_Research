package config

import (
	"fmt"
	"os"
	"strconv"
)

type Config struct {
	Port             string
	RedisURL         string
	JWTSecret        string
	AllowedOrigins   []string
	WriteBufferBytes int
}

func Load() (*Config, error) {
	c := &Config{
		Port:             envOr("REALTIME_PORT", "8001"),
		RedisURL:         os.Getenv("REDIS_URL"),
		JWTSecret:        os.Getenv("DJANGO_SECRET_KEY"),
		AllowedOrigins:   parseList(envOr("REALTIME_ALLOWED_ORIGINS", "*")),
		WriteBufferBytes: intEnvOr("REALTIME_WRITE_BUFFER_BYTES", 4096),
	}
	if c.RedisURL == "" {
		return nil, fmt.Errorf("REDIS_URL is required")
	}
	if c.JWTSecret == "" {
		return nil, fmt.Errorf("DJANGO_SECRET_KEY is required (must match Django's)")
	}
	return c, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func intEnvOr(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}

func parseList(s string) []string {
	if s == "" || s == "*" {
		return []string{"*"}
	}
	out := []string{}
	cur := ""
	for _, r := range s {
		if r == ',' {
			if cur != "" {
				out = append(out, cur)
				cur = ""
			}
			continue
		}
		if r == ' ' {
			continue
		}
		cur += string(r)
	}
	if cur != "" {
		out = append(out, cur)
	}
	return out
}
