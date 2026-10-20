resource "aws_api_gateway_rest_api" "partner" {
  name = "partner-api"
}

resource "aws_api_gateway_domain_name" "partner" {
  domain_name = "partner.acme.com"
}

resource "aws_api_gateway_base_path_mapping" "partner" {
  api_id      = aws_api_gateway_rest_api.partner.id
  domain_name = aws_api_gateway_domain_name.partner.domain_name
}

module "paths" {
  source = "../../modules/paths"
  endpoints = {
    pricing = {
      backend_fqdn = "pricing.acme.com"
      backend_path = "/v1/pricing"
    }
  }
}
