package fx

import "net/http"

const ratesURL = "https://api.exchangerate.host/latest"

func Rates() (*http.Response, error) { return http.Get(ratesURL) }
