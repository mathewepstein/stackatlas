import re

CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
FE_PREFIXES = (
    "VITE_", "NEXT_PUBLIC_", "NUXT_PUBLIC_", "VUE_APP_", "REACT_APP_", "PUBLIC_", "APP_",
    "URL_", "HOST_", "FEIGN_", "CLIENT_", "ENDPOINT_",
)
NAME_SUFFIXES = (
    "_BASE_URL", "_BASEURL", "_URL", "_URI", "_HOSTNAME", "_HOST", "_ENDPOINT", "_BASE",
    "_ORIGIN", "_DOMAIN", "_ADDRESS", "_ADDR", "_FQDN",
)
GENERIC_NAMES = {
    "base", "url", "uri", "api", "app", "host", "server", "service", "endpoint", "origin",
    "domain", "address", "addr", "backend", "frontend", "web", "client", "http", "https",
    "rest", "public", "fqdn",
}


def relax(key: str) -> str:
    return CAMEL.sub("_", key).lower().replace(".", "_").replace("-", "_")


def kebab(name: str) -> str:
    return CAMEL.sub("-", name).lower().replace("_", "-").replace(".", "-")


def var_to_name(var: str) -> str:
    name = CAMEL.sub("_", var).upper().replace(".", "_").replace("-", "_")
    for prefix in FE_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
            break
    for suffix in NAME_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    return name.lower().replace("_", "-")
