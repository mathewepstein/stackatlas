plugins {
    id("org.springframework.boot") version "3.3.0"
    kotlin("jvm") version "2.0.0"
    id("org.openapi.generator") version "7.10.0"
}

openApiGenerate {
    inputSpec.set("$projectDir/specs/inventory.yaml")
}
