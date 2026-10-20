variable "endpoints" {
  type = map(any)
}

resource "aws_api_gateway_integration" "path" {
  for_each = var.endpoints
  uri      = "https://${each.value.backend_fqdn}${each.value.backend_path}"
}
