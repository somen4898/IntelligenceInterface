package server

import (
	"fmt"
	"net/http"
)

func handleHealth(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "ok")
}

// ProcessRequest validates and processes an incoming request.
func ProcessRequest(w http.ResponseWriter, r *http.Request) error {
	if r.Method != http.MethodPost {
		return fmt.Errorf("invalid method: %s", r.Method)
	}
	return nil
}
