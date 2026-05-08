// Package auth verifies JWTs issued by Django's djangorestframework-simplejwt.
//
// The token is HS256-signed with Django's SECRET_KEY (we read it from the
// shared env). We verify the signature, the expiry, and that the token is an
// "access" token (not a refresh token), then extract user_id.
package auth

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

type Claims struct {
	UserID    int64  `json:"user_id"`
	TokenType string `json:"token_type"`
	jwt.RegisteredClaims
}

type Verifier struct {
	secret []byte
}

func NewVerifier(secret string) *Verifier {
	return &Verifier{secret: []byte(secret)}
}

func (v *Verifier) Verify(tokenStr string) (*Claims, error) {
	if tokenStr == "" {
		return nil, errors.New("empty token")
	}
	claims := &Claims{}
	tok, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (any, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return v.secret, nil
	})
	if err != nil {
		return nil, fmt.Errorf("parse: %w", err)
	}
	if !tok.Valid {
		return nil, errors.New("invalid token")
	}
	if claims.TokenType != "access" {
		return nil, fmt.Errorf("token_type must be 'access', got %q", claims.TokenType)
	}
	if claims.UserID == 0 {
		return nil, errors.New("missing user_id claim")
	}
	return claims, nil
}
