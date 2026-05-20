// Package main is the entry point for the application.
package main

import (
	"fmt"
	"example.com/myapp/server"
)

// Version is the application version.
var Version = "1.0.0"

// MaxRetries is the maximum number of retries.
const MaxRetries = 3

func main() {
	srv := server.NewServer(":8080")
	fmt.Println("Starting server on", srv.Addr)
	srv.Start()
}
