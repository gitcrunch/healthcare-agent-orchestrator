# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import json
import logging
import os

import yaml
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def setup_app_insights_logging(credential, log_level=logging.DEBUG) -> None:
    """Configure OpenTelemetry logging and tracing for Application Insights."""
    os.environ["OTEL_EXPERIMENTAL_RESOURCE_DETECTORS"] = "azure_app_service"
    trace.set_tracer_provider(TracerProvider())
    tracer_provider = trace.get_tracer_provider()

    # Configure Azure Monitor Exporter
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        exporter = AzureMonitorTraceExporter(
            connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
        )
        span_processor = BatchSpanProcessor(exporter)
        tracer_provider.add_span_processor(span_processor)

    # Instrument FastAPI
    FastAPIInstrumentor().instrument()

    # Instrument Logging
    LoggingInstrumentor().instrument(set_logging_format=True)

    # Configure Azure Monitor if connection string is set
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        configure_azure_monitor(
            credential=credential,
            logger=logging.getLogger(__name__),
            connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
            logging_exporter_enabled=True,
            tracing_exporter_enabled=True,
            metrics_exporter_enabled=True,
            enable_live_metrics=True,
            formatter=formatter
        )

    # Ensure all loggers propagate to root for Azure Monitor
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).propagate = True


def setup_logging(log_level=logging.DEBUG) -> None:
    # Create a logging handler to write logging records, in OTLP format, to the exporter.
    console_handler = logging.StreamHandler()

    # Add filters to the handler to only process records from semantic_kernel.
    # console_handler.addFilter(logging.Filter("semantic_kernel"))
    console_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(console_handler)
    logger.setLevel(log_level)


def load_agent_config(scenario: str) -> dict:
    src_dir = os.path.dirname(os.path.abspath(__file__))
    scenario_directory = os.path.join(src_dir, f"scenarios/{scenario}/config")

    agent_config_path = os.path.join(scenario_directory, "agents.yaml")
    excluded_agents = os.getenv("EXCLUDED_AGENTS", "").split(",")
    logger.info(f"Excluding agents: {excluded_agents}")

    with open(agent_config_path, "r", encoding="utf-8") as f:
        agent_config = yaml.safe_load(f)
        agent_config = [agent for agent in agent_config if agent["name"] not in excluded_agents]
        logger.info(
            f"Loaded agent configuration for scenario '{scenario}': {[agent['name'] for agent in agent_config]}")

    bot_ids = json.loads(os.getenv("BOT_IDS"))
    hls_model_endpoints = json.loads(os.getenv("HLS_MODEL_ENDPOINTS"))
    for agent in agent_config:
        agent["bot_id"] = bot_ids.get(agent["name"])
        agent["hls_model_endpoint"] = hls_model_endpoints
        if agent.get("addition_instructions"):
            for file in agent["addition_instructions"]:
                with open(os.path.join(scenario_directory, file)) as f:
                    agent["instructions"] += f.read()

    return agent_config


class DefaultConfig:
    """ Bot Configuration """

    def __init__(self, botId):
        self.APP_ID = botId
        self.APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
        self.APP_TYPE = os.environ.get("MicrosoftAppType", "MultiTenant")
        self.APP_TENANTID = os.environ.get("MicrosoftAppTenantId", "")
