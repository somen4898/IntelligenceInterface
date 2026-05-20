// Package server provides HTTP server functionality.
package server

import "net/http"

// Server handles HTTP requests.
type Server struct {
	Addr   string
	mux    *http.ServeMux
}

// Config holds server configuration.
type Config struct {
	Addr    string
	Timeout int
}

// Handler defines the interface for request handlers.
type Handler interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
	Health() bool
}

// NewServer creates a new server instance.
func NewServer(addr string) *Server {
	return &Server{
		Addr: addr,
		mux:  http.NewServeMux(),
	}
}

// Start begins listening for requests.
func (s *Server) Start() error {
	s.mux.HandleFunc("/health", handleHealth)
	return http.ListenAndServe(s.Addr, s.mux)
}

// Stop gracefully shuts down the server.
func (s *Server) Stop() error {
	return nil
}
