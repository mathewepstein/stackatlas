package pricing

import (
	"net/http"
	"os"
)

// Docs: https://wiki.thirdparty.io/inventory
func Quote(sku string) (*http.Response, error) {
	base := os.Getenv("PRICING_URL")
	return http.Get(base + "/quote/" + sku)
}
