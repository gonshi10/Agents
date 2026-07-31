"""Core techstack agent implementation.

Monitors monthly technology adoption shifts in tracked companies' job postings
and emails a digest focused on products, vendors, and adopting employers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from common.clients.adzuna import AdzunaClient
from common.clients.openai_client import OpenAIClient
from common.config import Settings
from common.email import templates as et
from common.email.sender import EmailSender
from common.watchlist import load_companies

from .prompts import (
    BATCH_TEMPLATE_HEADER,
    MARKET_OVERVIEW_TEMPLATE,
    SINGLE_TECHNOLOGY_TEMPLATE,
    SYSTEM_PROMPT,
)

TECH_KEYWORDS: dict[str, list[str]] = {
    # Web & Backend Frameworks
    "React": [r"\breact\b(?!\.js| native)"],
    "Next.js": [r"\bnext\.js\b", r"\bnextjs\b"],
    "Vue.js": [r"\bvue\.js\b", r"\bvuejs\b", r"\bvue\b"],
    "Angular": [r"\bangular\b"],
    "Svelte": [r"\bsvelte\b"],
    "Remix": [r"\bremix\b(?! os)"],
    "Astro": [r"\bastro\b(?! physics)"],
    "htmx": [r"\bhtmx\b"],
    "Django": [r"\bdjango\b"],
    "FastAPI": [r"\bfastapi\b"],
    "Flask": [r"\bflask\b"],
    "Express.js": [r"\bexpress\.js\b", r"\bexpressjs\b"],
    "NestJS": [r"\bnestjs\b", r"\bnest\.js\b"],
    "Spring Boot": [r"\bspring boot\b", r"\bspring framework\b"],
    "Laravel": [r"\blaravel\b"],
    "Rails": [r"\bruby on rails\b", r"\brails\b"],
    "Phoenix": [r"\bphoenix framework\b"],
    "Actix": [r"\bactix\b"],
    "Axum": [r"\baxum\b"],
    "Gin": [r"\bgin framework\b", r"\bgin-gonic\b"],
    "Fiber": [r"\bfiber framework\b"],
    "Ktor": [r"\bktor\b"],
    "Quarkus": [r"\bquarkus\b"],
    "Micronaut": [r"\bmicronaut\b"],
    "ASP.NET": [r"\basp\.net\b"],
    "Blazor": [r"\bblazor\b"],
    "tRPC": [r"\btrpc\b"],
    "GraphQL": [r"\bgraphql\b"],
    "gRPC": [r"\bgrpc\b"],
    # Databases - Relational
    "PostgreSQL": [r"\bpostgresql\b", r"\bpostgres\b"],
    "MySQL": [r"\bmysql\b"],
    "SQLite": [r"\bsqlite\b"],
    "MariaDB": [r"\bmariadb\b"],
    "CockroachDB": [r"\bcockroachdb\b"],
    "YugabyteDB": [r"\byugabyte\b"],
    # Databases - NoSQL
    "MongoDB": [r"\bmongodb\b"],
    "Redis": [r"\bredis\b"],
    "Cassandra": [r"\bcassandra\b"],
    "DynamoDB": [r"\bdynamodb\b"],
    "Couchbase": [r"\bcouchbase\b"],
    "HBase": [r"\bhbase\b"],
    "ScyllaDB": [r"\bscylladb\b"],
    "RocksDB": [r"\brocksdb\b"],
    "DuckDB": [r"\bduckdb\b"],
    # Databases - Analytics
    "Snowflake": [r"\bsnowflake\b"],
    "BigQuery": [r"\bbigquery\b"],
    "Redshift": [r"\bredshift\b"],
    "ClickHouse": [r"\bclickhouse\b"],
    "Databricks": [r"\bdatabricks\b"],
    "Pinot": [r"\bapache pinot\b"],
    "Druid": [r"\bapache druid\b"],
    "Trino": [r"\btrino\b", r"\bpresto\b"],
    # Databases - Search
    "Elasticsearch": [r"\belasticsearch\b"],
    "OpenSearch": [r"\bopensearch\b"],
    "Solr": [r"\bsolr\b"],
    # Databases - Graph
    "Neo4j": [r"\bneo4j\b"],
    "ArangoDB": [r"\barangodb\b"],
    "TigerGraph": [r"\btigergraph\b"],
    # Databases - Vector / AI
    "Pinecone": [r"\bpinecone\b"],
    "Weaviate": [r"\bweaviate\b"],
    "Chroma": [r"\bchroma\b(?!key)"],
    "Qdrant": [r"\bqdrant\b"],
    "Milvus": [r"\bmilvus\b"],
    "pgvector": [r"\bpgvector\b"],
    # Databases - Time Series
    "TimescaleDB": [r"\btimescaledb\b"],
    "InfluxDB": [r"\binfluxdb\b"],
    "VictoriaMetrics": [r"\bvictoriametrics\b"],
    # Cloud Platforms
    "AWS": [r"\baws\b", r"\bamazon web services\b"],
    "GCP": [r"\bgcp\b", r"\bgoogle cloud\b"],
    "Azure": [r"\bazure\b"],
    "Oracle Cloud": [r"\boracle cloud\b"],
    "Cloudflare": [r"\bcloudflare\b"],
    "DigitalOcean": [r"\bdigitalocean\b"],
    "Vercel": [r"\bvercel\b"],
    "Fly.io": [r"\bfly\.io\b"],
    # DevOps & Infra
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Docker": [r"\bdocker\b"],
    "Terraform": [r"\bterraform\b"],
    "Ansible": [r"\bansible\b"],
    "Helm": [r"\bhelm\b(?! chart)?"],
    "ArgoCD": [r"\bargocd\b", r"\bargo cd\b"],
    "Flux": [r"\bfluxcd\b", r"\bflux cd\b"],
    "Pulumi": [r"\bpulumi\b"],
    "HashiCorp Vault": [r"\bvault\b(?! of| keeper)"],
    "Consul": [r"\bconsul\b(?! general)"],
    "Nomad": [r"\bnomad\b(?! land)"],
    "Istio": [r"\bistio\b"],
    "Envoy": [r"\benvoy proxy\b", r"\benvoy\b"],
    "Linkerd": [r"\blinkerd\b"],
    "Bazel": [r"\bbazel\b"],
    "Nix": [r"\bnix\b(?! os)?", r"\bnixos\b"],
    # CI/CD
    "GitHub Actions": [r"\bgithub actions\b"],
    "GitLab CI": [r"\bgitlab ci\b", r"\bgitlab\b"],
    "Jenkins": [r"\bjenkins\b"],
    "CircleCI": [r"\bcircleci\b"],
    "Tekton": [r"\btekton\b"],
    "Spinnaker": [r"\bspinnaker\b"],
    # Observability
    "Prometheus": [r"\bprometheus\b"],
    "Grafana": [r"\bgrafana\b"],
    "Datadog": [r"\bdatadog\b"],
    "OpenTelemetry": [r"\bopentelemetry\b", r"\botel\b"],
    "Jaeger": [r"\bjaeger\b"],
    "Loki": [r"\bloki\b(?! blockchain)"],
    "Sentry": [r"\bsentry\b(?!\.io)?"],
    "Splunk": [r"\bsplunk\b"],
    "Honeycomb": [r"\bhoneycomb\.io\b"],
    "New Relic": [r"\bnew relic\b"],
    "Dynatrace": [r"\bdynatrace\b"],
    # Messaging / Streaming
    "Kafka": [r"\bkafka\b"],
    "RabbitMQ": [r"\brabbitmq\b"],
    "NATS": [r"\bnats\b(?!ure)"],
    "Pulsar": [r"\bapache pulsar\b"],
    "Temporal": [r"\btemporal\.io\b", r"\btemporal workflow\b"],
    "Celery": [r"\bcelery\b"],
    # Data Engineering / Analytics
    "Apache Spark": [r"\bapache spark\b", r"\bpyspark\b"],
    "Apache Flink": [r"\bapache flink\b", r"\bflink\b"],
    "Apache Beam": [r"\bapache beam\b"],
    "dbt": [r"\bdbt\b"],
    "Airflow": [r"\bairflow\b", r"\bapache airflow\b"],
    "Prefect": [r"\bprefect\b"],
    "Dagster": [r"\bdagster\b"],
    "Fivetran": [r"\bfivetran\b"],
    "Airbyte": [r"\bairbyte\b"],
    "Delta Lake": [r"\bdelta lake\b"],
    "Apache Iceberg": [r"\biceberg\b"],
    "Apache Hudi": [r"\bhudi\b"],
    "Polars": [r"\bpolars\b"],
    "Dask": [r"\bdask\b"],
    "Ray": [r"\bray\.io\b", r"\banyscale\b"],
    "Great Expectations": [r"\bgreat expectations\b"],
    "Apache Arrow": [r"\bapache arrow\b"],
    "Tableau": [r"\btableau\b"],
    "Looker": [r"\blooker\b"],
    "Metabase": [r"\bmetabase\b"],
    "Apache Superset": [r"\bsuperset\b"],
    # AI / ML
    "PyTorch": [r"\bpytorch\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "JAX": [r"\bjax\b"],
    "Keras": [r"\bkeras\b"],
    "scikit-learn": [r"\bscikit-learn\b", r"\bsklearn\b"],
    "XGBoost": [r"\bxgboost\b"],
    "LightGBM": [r"\blightgbm\b"],
    "CatBoost": [r"\bcatboost\b"],
    "Hugging Face": [r"\bhugging face\b", r"\bhuggingface\b"],
    "LangChain": [r"\blangchain\b"],
    "LlamaIndex": [r"\bllamaindex\b", r"\bllama.index\b"],
    "AutoGen": [r"\bautogen\b"],
    "CrewAI": [r"\bcrewai\b"],
    "vLLM": [r"\bvllm\b"],
    "llama.cpp": [r"\bllama\.cpp\b"],
    "Ollama": [r"\bollama\b"],
    "TensorRT": [r"\btensorrt\b"],
    "ONNX": [r"\bonnx\b"],
    "MLflow": [r"\bmlflow\b"],
    "Weights & Biases": [r"\bweights\s*&\s*biases\b", r"\bwandb\b"],
    "BentoML": [r"\bbentoml\b"],
    "Triton": [r"\btriton inference\b"],
    "OpenAI API": [r"\bopenai api\b", r"\bgpt-4\b", r"\bgpt-3\b"],
    "Anthropic API": [r"\banthropic\b", r"\bclaude api\b"],
    "Gemini": [r"\bgemini\b(?! south)"],
    "Cohere": [r"\bcohere\b"],
    "Mistral": [r"\bmistral\b(?! wind)"],
    "Stable Diffusion": [r"\bstable diffusion\b"],
    "CLIP": [r"\bclip\b(?! art)"],
    # Bioinformatics & Life Sciences
    "Biopython": [r"\bbiopython\b"],
    "Bioconductor": [r"\bbioconductor\b"],
    "GATK": [r"\bgatk\b"],
    "BWA": [r"\bbwa\b(?! motor)"],
    "Bowtie": [r"\bbowtie\b"],
    "STAR Aligner": [r"\bstar aligner\b"],
    "DESeq2": [r"\bdeseq2\b"],
    "Seurat": [r"\bseurat\b"],
    "Scanpy": [r"\bscanpy\b"],
    "AlphaFold": [r"\balphafold\b"],
    "RoseTTAFold": [r"\brosettafold\b"],
    "PyMOL": [r"\bpymol\b"],
    "GROMACS": [r"\bgromacs\b"],
    "AMBER": [r"\bamber\b(?! alert)"],
    "OpenMM": [r"\bopenmm\b"],
    "RDKit": [r"\brdkit\b"],
    "DeepChem": [r"\bdeepchem\b"],
    "Nextflow": [r"\bnextflow\b"],
    "Snakemake": [r"\bsnakemake\b"],
    "Galaxy": [r"\bgalaxy platform\b", r"\bgalaxy bioinformatics\b"],
    "CellRanger": [r"\bcellranger\b"],
    "BLAST": [r"\bblast\b(?! radius)"],
    "HMMER": [r"\bhmmer\b"],
    "ITK": [r"\bitk\b(?! toolbox)"],
    "SimpleITK": [r"\bsimpleitk\b"],
    "3D Slicer": [r"\b3d slicer\b"],
    "Napari": [r"\bnapari\b"],
    # Quantum
    "Qiskit": [r"\bqiskit\b"],
    "Cirq": [r"\bcirq\b"],
    "PennyLane": [r"\bpennylane\b"],
    "Amazon Braket": [r"\bamazon braket\b"],
    "Q#": [r"\bq#\b", r"\bq sharp\b"],
    "QuTiP": [r"\bqutip\b"],
    # Engineering Simulation
    "ANSYS": [r"\bansys\b"],
    "COMSOL": [r"\bcomsol\b"],
    "OpenFOAM": [r"\bopenfoam\b"],
    "FEniCS": [r"\bfenics\b"],
    "Abaqus": [r"\babaqus\b"],
    "NASTRAN": [r"\bnastran\b"],
    "ParaView": [r"\bparaview\b"],
    "Simulink": [r"\bsimulink\b"],
    "LabVIEW": [r"\blabview\b"],
    "SolidWorks": [r"\bsolidworks\b"],
    "CATIA": [r"\bcatia\b"],
    "Modelica": [r"\bmodelica\b"],
    "OpenSCAD": [r"\bopenscad\b"],
    # HPC
    "MPI": [r"\bmpi\b(?! format)"],
    "OpenMP": [r"\bopenmp\b"],
    "CUDA": [r"\bcuda\b"],
    "HIP": [r"\bhip\b(?! hop| pain)"],
    "OpenCL": [r"\bopencl\b"],
    "SYCL": [r"\bsycl\b"],
    "BLAS": [r"\bblas\b"],
    "LAPACK": [r"\blapack\b"],
    "PETSc": [r"\bpetsc\b"],
    "HDF5": [r"\bhdf5\b"],
    "NetCDF": [r"\bnetcdf\b"],
    "Zarr": [r"\bzarr\b"],
    "xarray": [r"\bxarray\b"],
    "NumPy": [r"\bnumpy\b"],
    "SciPy": [r"\bscipy\b"],
    "FFTW": [r"\bfftw\b"],
    "deal.II": [r"\bdeal\.ii\b"],
    "Firedrake": [r"\bfiredrake\b"],
    # Cybersecurity
    "Metasploit": [r"\bmetasploit\b"],
    "Burp Suite": [r"\bburp suite\b"],
    "Wireshark": [r"\bwireshark\b"],
    "Nmap": [r"\bnmap\b"],
    "Snort": [r"\bsnort\b"],
    "Suricata": [r"\bsuricata\b"],
    "Zeek": [r"\bzeek\b"],
    "YARA": [r"\byara\b"],
    "Wazuh": [r"\bwazuh\b"],
    "OpenVAS": [r"\bopenvas\b"],
    "CrowdStrike": [r"\bcrowdstrike\b"],
    "SentinelOne": [r"\bsentinelone\b"],
    "Falco": [r"\bfalco\b(?! falcon)"],
    # Robotics & Embedded
    "ROS": [r"\bros 2\b", r"\bros2\b", r"\brobot operating system\b"],
    "MoveIt": [r"\bmoveit\b"],
    "Gazebo": [r"\bgazebo\b"],
    "FreeRTOS": [r"\bfreertos\b"],
    "Zephyr RTOS": [r"\bzephyr rtos\b", r"\bzephyr project\b"],
    "PX4": [r"\bpx4\b"],
    "ArduPilot": [r"\bardupilot\b"],
    "Arduino": [r"\barduino\b"],
    "micro-ROS": [r"\bmicro-ros\b"],
    # Computer Vision
    "OpenCV": [r"\bopencv\b"],
    "YOLO": [r"\byolo\b"],
    "Detectron2": [r"\bdetectron2\b"],
    "SAM": [r"\bsegment anything\b"],
    "Ultralytics": [r"\bultralytics\b"],
    "Kornia": [r"\bkornia\b"],
    "Albumentations": [r"\balbumentations\b"],
    # Geospatial
    "QGIS": [r"\bqgis\b"],
    "ArcGIS": [r"\barcgis\b"],
    "GDAL": [r"\bgdal\b"],
    "GeoPandas": [r"\bgeopandas\b"],
    "PostGIS": [r"\bpostgis\b"],
    "Google Earth Engine": [r"\bearth engine\b"],
    "Mapbox": [r"\bmapbox\b"],
    "Rasterio": [r"\brasterio\b"],
    "PyProj": [r"\bpyproj\b"],
    # Blockchain / Web3
    "Solidity": [r"\bsolidity\b"],
    "Hardhat": [r"\bhardhat\b"],
    "Foundry": [r"\bfoundry\b(?! vtt)"],
    "Web3.py": [r"\bweb3\.py\b"],
    "ethers.js": [r"\bethers\.js\b"],
    "Chainlink": [r"\bchainlink\b"],
    "OpenZeppelin": [r"\bopenzeppelin\b"],
    "Anchor": [r"\banchor framework\b", r"\bsolana anchor\b"],
    "The Graph": [r"\bthe graph\b(?! api| network)"],
    "IPFS": [r"\bipfs\b"],
    # Audio / Signal
    "LibROSA": [r"\blibrosa\b"],
    "torchaudio": [r"\btorchaudio\b"],
    "Whisper": [r"\bwhisper\b(?! quiet| soft)"],
    "ESPnet": [r"\bespnet\b"],
    "Kaldi": [r"\bkaldi\b"],
    "FFmpeg": [r"\bffmpeg\b"],
    "GStreamer": [r"\bgstreamer\b"],
    "WebRTC": [r"\bwebrtc\b"],
    # Finance / Quant
    "QuantLib": [r"\bquantlib\b"],
    "Zipline": [r"\bzipline\b"],
    "Backtrader": [r"\bbacktrader\b"],
    "Alpaca API": [r"\balpaca api\b"],
    "Bloomberg API": [r"\bbloomberg api\b", r"\bblpapi\b"],
    "QuantConnect": [r"\bquantconnect\b"],
    # Mobile
    "React Native": [r"\breact native\b"],
    "Flutter": [r"\bflutter\b"],
    "SwiftUI": [r"\bswiftui\b"],
    "Jetpack Compose": [r"\bjetpack compose\b"],
    "Expo": [r"\bexpo\b(?! marker)"],
    "Capacitor": [r"\bcapacitor\b"],
    # Testing
    "pytest": [r"\bpytest\b"],
    "Jest": [r"\bjest\b"],
    "Cypress": [r"\bcypress\b"],
    "Playwright": [r"\bplaywright\b"],
    "Selenium": [r"\bselenium\b"],
    "k6": [r"\bk6\b(?! plus)"],
    "Locust": [r"\blocust\b(?!s)"],
    "Storybook": [r"\bstorybook\b"],
}

TECH_CATEGORY_SETS: dict[str, set[str]] = {
    "WebAndBackend": {
        "React",
        "Next.js",
        "Vue.js",
        "Angular",
        "Svelte",
        "Remix",
        "Astro",
        "htmx",
        "Django",
        "FastAPI",
        "Flask",
        "Express.js",
        "NestJS",
        "Spring Boot",
        "Laravel",
        "Rails",
        "Phoenix",
        "Actix",
        "Axum",
        "Gin",
        "Fiber",
        "Ktor",
        "Quarkus",
        "Micronaut",
        "ASP.NET",
        "Blazor",
        "tRPC",
        "GraphQL",
        "gRPC",
    },
    "DataPlatforms": {
        "PostgreSQL",
        "MySQL",
        "SQLite",
        "MariaDB",
        "CockroachDB",
        "YugabyteDB",
        "MongoDB",
        "Redis",
        "Cassandra",
        "DynamoDB",
        "Couchbase",
        "HBase",
        "ScyllaDB",
        "RocksDB",
        "DuckDB",
        "Snowflake",
        "BigQuery",
        "Redshift",
        "ClickHouse",
        "Databricks",
        "Pinot",
        "Druid",
        "Trino",
        "Elasticsearch",
        "OpenSearch",
        "Solr",
        "Neo4j",
        "ArangoDB",
        "TigerGraph",
        "Pinecone",
        "Weaviate",
        "Chroma",
        "Qdrant",
        "Milvus",
        "pgvector",
        "TimescaleDB",
        "InfluxDB",
        "VictoriaMetrics",
    },
    "CloudInfraDevOps": {
        "AWS",
        "GCP",
        "Azure",
        "Oracle Cloud",
        "Cloudflare",
        "DigitalOcean",
        "Vercel",
        "Fly.io",
        "Kubernetes",
        "Docker",
        "Terraform",
        "Ansible",
        "Helm",
        "ArgoCD",
        "Flux",
        "Pulumi",
        "HashiCorp Vault",
        "Consul",
        "Nomad",
        "Istio",
        "Envoy",
        "Linkerd",
        "Bazel",
        "Nix",
        "GitHub Actions",
        "GitLab CI",
        "Jenkins",
        "CircleCI",
        "Tekton",
        "Spinnaker",
        "Prometheus",
        "Grafana",
        "Datadog",
        "OpenTelemetry",
        "Jaeger",
        "Loki",
        "Sentry",
        "Splunk",
        "Honeycomb",
        "New Relic",
        "Dynatrace",
        "Kafka",
        "RabbitMQ",
        "NATS",
        "Pulsar",
        "Temporal",
        "Celery",
    },
    "DataEngineeringAnalytics": {
        "Apache Spark",
        "Apache Flink",
        "Apache Beam",
        "dbt",
        "Airflow",
        "Prefect",
        "Dagster",
        "Fivetran",
        "Airbyte",
        "Delta Lake",
        "Apache Iceberg",
        "Apache Hudi",
        "Polars",
        "Dask",
        "Ray",
        "Great Expectations",
        "Apache Arrow",
        "Tableau",
        "Looker",
        "Metabase",
        "Apache Superset",
    },
    "AIAndML": {
        "PyTorch",
        "TensorFlow",
        "JAX",
        "Keras",
        "scikit-learn",
        "XGBoost",
        "LightGBM",
        "CatBoost",
        "Hugging Face",
        "LangChain",
        "LlamaIndex",
        "AutoGen",
        "CrewAI",
        "vLLM",
        "llama.cpp",
        "Ollama",
        "TensorRT",
        "ONNX",
        "MLflow",
        "Weights & Biases",
        "BentoML",
        "Triton",
        "OpenAI API",
        "Anthropic API",
        "Gemini",
        "Cohere",
        "Mistral",
        "Stable Diffusion",
        "CLIP",
    },
    "BioAndLifeSciences": {
        "Biopython",
        "Bioconductor",
        "GATK",
        "BWA",
        "Bowtie",
        "STAR Aligner",
        "DESeq2",
        "Seurat",
        "Scanpy",
        "AlphaFold",
        "RoseTTAFold",
        "PyMOL",
        "GROMACS",
        "AMBER",
        "OpenMM",
        "RDKit",
        "DeepChem",
        "Nextflow",
        "Snakemake",
        "Galaxy",
        "CellRanger",
        "BLAST",
        "HMMER",
        "ITK",
        "SimpleITK",
        "3D Slicer",
        "Napari",
    },
    "Quantum": {"Qiskit", "Cirq", "PennyLane", "Amazon Braket", "Q#", "QuTiP"},
    "SimulationAndHPC": {
        "ANSYS",
        "COMSOL",
        "OpenFOAM",
        "FEniCS",
        "Abaqus",
        "NASTRAN",
        "ParaView",
        "Simulink",
        "LabVIEW",
        "SolidWorks",
        "CATIA",
        "Modelica",
        "OpenSCAD",
        "MPI",
        "OpenMP",
        "CUDA",
        "HIP",
        "OpenCL",
        "SYCL",
        "BLAS",
        "LAPACK",
        "PETSc",
        "HDF5",
        "NetCDF",
        "Zarr",
        "xarray",
        "NumPy",
        "SciPy",
        "FFTW",
        "deal.II",
        "Firedrake",
    },
    "Cybersecurity": {
        "Metasploit",
        "Burp Suite",
        "Wireshark",
        "Nmap",
        "Snort",
        "Suricata",
        "Zeek",
        "YARA",
        "Wazuh",
        "OpenVAS",
        "CrowdStrike",
        "SentinelOne",
        "Falco",
    },
    "RoboticsAndEmbedded": {
        "ROS",
        "MoveIt",
        "Gazebo",
        "FreeRTOS",
        "Zephyr RTOS",
        "PX4",
        "ArduPilot",
        "Arduino",
        "micro-ROS",
    },
    "ComputerVision": {"OpenCV", "YOLO", "Detectron2", "SAM", "Ultralytics", "Kornia", "Albumentations"},
    "Geospatial": {
        "QGIS",
        "ArcGIS",
        "GDAL",
        "GeoPandas",
        "PostGIS",
        "Google Earth Engine",
        "Mapbox",
        "Rasterio",
        "PyProj",
    },
    "Web3AndBlockchain": {
        "Solidity",
        "Hardhat",
        "Foundry",
        "Web3.py",
        "ethers.js",
        "Chainlink",
        "OpenZeppelin",
        "Anchor",
        "The Graph",
        "IPFS",
    },
    "AudioAndSignal": {"LibROSA", "torchaudio", "Whisper", "ESPnet", "Kaldi", "FFmpeg", "GStreamer", "WebRTC"},
    "FinanceAndQuant": {"QuantLib", "Zipline", "Backtrader", "Alpaca API", "Bloomberg API", "QuantConnect"},
    "Mobile": {"React Native", "Flutter", "SwiftUI", "Jetpack Compose", "Expo", "Capacitor"},
    "Testing": {"pytest", "Jest", "Cypress", "Playwright", "Selenium", "k6", "Locust", "Storybook"},
}

TECH_CATEGORY_MAP: dict[str, str] = {
    tech: category for category, technologies in TECH_CATEGORY_SETS.items() for tech in technologies
}

CATEGORY_EXPERT_MAP: dict[str, str] = {
    "WebAndBackend": "Web & Backend Specialist",
    "DataPlatforms": "Data Infrastructure Analyst",
    "CloudInfraDevOps": "Cloud & DevOps Specialist",
    "DataEngineeringAnalytics": "Data Engineering Analyst",
    "AIAndML": "AI/ML Platform Analyst",
    "BioAndLifeSciences": "Life Sciences Tech Analyst",
    "Quantum": "Quantum Computing Analyst",
    "SimulationAndHPC": "HPC & Simulation Analyst",
    "Cybersecurity": "Cybersecurity Specialist",
    "RoboticsAndEmbedded": "Robotics & Embedded Systems Analyst",
    "ComputerVision": "Computer Vision Analyst",
    "Geospatial": "Geospatial Tech Analyst",
    "Web3AndBlockchain": "Web3 & Blockchain Analyst",
    "AudioAndSignal": "Audio & Signal Processing Analyst",
    "FinanceAndQuant": "Quantitative Finance Analyst",
    "Mobile": "Mobile Platform Analyst",
    "Testing": "QA & Testing Specialist",
    "GeneralTech": "Enterprise Technology Analyst",
}

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "WebAndBackend": "Web & Backend",
    "DataPlatforms": "Data Platforms",
    "CloudInfraDevOps": "Cloud & DevOps",
    "DataEngineeringAnalytics": "Data Engineering & Analytics",
    "AIAndML": "AI & ML",
    "BioAndLifeSciences": "Life Sciences",
    "Quantum": "Quantum Computing",
    "SimulationAndHPC": "HPC & Simulation",
    "Cybersecurity": "Cybersecurity",
    "RoboticsAndEmbedded": "Robotics & Embedded",
    "ComputerVision": "Computer Vision",
    "Geospatial": "Geospatial",
    "Web3AndBlockchain": "Web3 & Blockchain",
    "AudioAndSignal": "Audio & Signal",
    "FinanceAndQuant": "Finance & Quant",
    "Mobile": "Mobile",
    "Testing": "Testing & QA",
    "GeneralTech": "General Tech",
}

SNAPSHOT_VERSION = 2


class TechstackAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            calls_per_minute=3,
        )
        self.email_sender = EmailSender(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_pass=settings.smtp_pass,
            default_to=settings.email_to,
        )
        self.trend_threshold = settings.techstack_trend_threshold
        self.lookback_days = settings.techstack_lookback_days
        self.snapshot_path = Path(settings.techstack_snapshot)

        self.client = (
            AdzunaClient(app_id=settings.adzuna_app_id, app_key=settings.adzuna_app_key)
            if settings.adzuna_app_id and settings.adzuna_app_key
            else None
        )
        self._compiled_patterns: dict[str, list[re.Pattern[str]]] | None = None
        self._company_sector_lookup: dict[str, str] = {}

        print("✓ Configuration loaded successfully")
        if self.client:
            print("🧰 Adzuna client initialized")
        else:
            print("⚠️ ADZUNA_APP_ID/ADZUNA_APP_KEY not set - techstack agent will be a no-op")
        if self.openai.is_enabled:
            print("✅ OpenAI SDK client initialized")
        else:
            print("⚠️ OpenAI API key not set - AI insights will be disabled")

    def _ensure_compiled_patterns(self) -> dict[str, list[re.Pattern[str]]]:
        if self._compiled_patterns is None:
            self._compiled_patterns = {
                tech: [re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns]
                for tech, patterns in TECH_KEYWORDS.items()
            }
        return self._compiled_patterns

    def extract_tech_mentions(self, postings: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
        """Return mention counts per technology and total postings scanned."""
        counts: dict[str, int] = {}
        compiled = self._ensure_compiled_patterns()
        total = 0

        for posting in postings:
            title = str(posting.get("title", ""))
            description = str(posting.get("description", ""))
            text = f"{title}\n{description}".strip()
            if not text:
                continue
            total += 1
            for tech, patterns in compiled.items():
                if any(pattern.search(text) for pattern in patterns):
                    counts[tech] = counts.get(tech, 0) + 1

        return counts, total

    @staticmethod
    def technology_category(technology: str) -> str:
        return TECH_CATEGORY_MAP.get(technology, "GeneralTech")

    def detect_company_trends(
        self,
        company: dict[str, Any],
        current_counts: dict[str, int],
        current_total: int,
        previous_entry: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        previous_entry = previous_entry or {}
        previous_counts = previous_entry.get("technologies", {}) or {}
        previous_total = int(previous_entry.get("total", 0) or 0)

        trends: list[dict[str, Any]] = []
        all_tech = set(current_counts) | set(previous_counts)
        for technology in sorted(all_tech):
            current_count = int(current_counts.get(technology, 0) or 0)
            previous_count = int(previous_counts.get(technology, 0) or 0)
            current_share = (current_count / current_total * 100.0) if current_total > 0 else 0.0
            previous_share = (previous_count / previous_total * 100.0) if previous_total > 0 else 0.0
            delta = current_share - previous_share

            direction: str | None = None
            if previous_count == 0 and current_count >= 3 and current_share >= 5.0:
                direction = "NEW"
            elif delta >= self.trend_threshold:
                direction = "RISING"
            elif previous_share >= 5.0 and (-delta) >= self.trend_threshold:
                direction = "FALLING"

            if direction:
                trends.append(
                    {
                        "company": company["company"],
                        "ticker": company.get("ticker"),
                        "technology": technology,
                        "category": self.technology_category(technology),
                        "direction": direction,
                        "current_count": current_count,
                        "previous_count": previous_count,
                        "current_share": round(current_share, 2),
                        "previous_share": round(previous_share, 2),
                        "delta_share": round(delta, 2),
                    }
                )
        return trends

    @staticmethod
    def detect_cross_company_trends(company_trends: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for trend in company_trends:
            tech = trend["technology"]
            entry = grouped.setdefault(
                tech,
                {
                    "category": trend.get("category", "GeneralTech"),
                    "rising": [],
                    "new": [],
                    "falling": [],
                    "deltas": [],
                    "market_wide": False,
                },
            )
            direction = trend["direction"]
            if direction == "RISING":
                entry["rising"].append(trend["company"])
                entry["deltas"].append(float(trend["delta_share"]))
            elif direction == "NEW":
                entry["new"].append(trend["company"])
                entry["deltas"].append(float(trend["delta_share"]))
            elif direction == "FALLING":
                entry["falling"].append(trend["company"])
                entry["deltas"].append(float(abs(trend["delta_share"])))

        for entry in grouped.values():
            deltas = entry.get("deltas", [])
            entry["avg_delta"] = round(sum(deltas) / len(deltas), 2) if deltas else 0.0
            entry["market_wide"] = (len(entry["rising"]) + len(entry["new"])) >= 2
            entry.pop("deltas", None)
        return grouped

    @staticmethod
    def summarize_category_momentum(signals: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = {}
        for signal in signals.values():
            category = str(signal.get("category", "GeneralTech"))
            bucket = summary.setdefault(
                category,
                {"rising": 0, "new": 0, "falling": 0, "market_wide": 0, "avg_deltas": []},
            )
            bucket["rising"] += len(signal.get("rising", []))
            bucket["new"] += len(signal.get("new", []))
            bucket["falling"] += len(signal.get("falling", []))
            if signal.get("market_wide"):
                bucket["market_wide"] += 1
            bucket["avg_deltas"].append(float(signal.get("avg_delta", 0.0) or 0.0))

        for bucket in summary.values():
            avg = bucket["avg_deltas"]
            bucket["avg_delta"] = round(sum(avg) / len(avg), 2) if avg else 0.0
            bucket.pop("avg_deltas", None)
        return summary

    @staticmethod
    def get_category_expert(category: str) -> str:
        return CATEGORY_EXPERT_MAP.get(category, "Enterprise Technology Analyst")

    @staticmethod
    def get_category_display_name(category: str) -> str:
        return CATEGORY_DISPLAY_NAMES.get(category, category.replace("_", " "))

    @staticmethod
    def build_company_sector_lookup(companies: list[dict[str, Any]]) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for company in companies:
            name = str(company.get("company", "")).strip()
            sector = str(company.get("sector") or "Unknown").strip()
            if name:
                lookup[name] = sector
                lookup[name.lower()] = sector
        return lookup

    @staticmethod
    def summarize_adopter_sectors(signal: dict[str, Any], lookup: dict[str, str]) -> str:
        companies = signal.get("rising", []) + signal.get("new", []) + signal.get("falling", [])
        sector_counts: dict[str, int] = {}
        for company in companies:
            sector = lookup.get(str(company), lookup.get(str(company).lower(), "Unknown"))
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if not sector_counts:
            return "None"
        return ", ".join(
            f"{sector} ({count})"
            for sector, count in sorted(sector_counts.items(), key=lambda item: (-item[1], item[0]))
        )

    @staticmethod
    def _format_category_momentum(category_summary: dict[str, dict[str, Any]]) -> str:
        lines: list[str] = []
        for category, bucket in sorted(category_summary.items()):
            lines.append(
                f"- {category}: {bucket['rising']} rising, {bucket['new']} new, "
                f"{bucket['falling']} falling, {bucket['market_wide']} market-wide"
            )
        return "\n".join(lines) if lines else "No category momentum detected."

    @staticmethod
    def _is_meaningful_insight(text: str) -> bool:
        if not text or len(text.strip()) < 40:
            return False
        lowered = text.lower()
        list_markers = ["rising at", "new at", "falling at", "rising:", "new:", "falling:"]
        if sum(1 for marker in list_markers if marker in lowered) >= 2:
            return False
        mechanism_keywords = [
            "suggest",
            "signal",
            "indicate",
            "implies",
            "because",
            "driver",
            "demand",
            "shift",
            "position",
            "competitive",
            "revenue",
            "adoption",
            "vendor",
            "platform",
        ]
        return any(keyword in lowered for keyword in mechanism_keywords)

    @staticmethod
    def _parse_investment_view(raw: str) -> dict[str, str]:
        text = raw.strip()
        if not text or text.upper() == "N/A":
            return {"rating": "WATCH", "reasoning": ""}

        reasoning = ""
        for sep in (" - ", " – ", " — ", ": "):
            if sep in text:
                parts = text.split(sep, 1)
                if parts[1].strip():
                    reasoning = parts[1].strip()
                    break

        upper = text.upper()
        rating = "WATCH"
        for candidate in ("AVOID", "BUY", "WATCH"):
            if upper.startswith(candidate):
                rating = candidate
                break
        else:
            for candidate in ("AVOID", "BUY", "WATCH"):
                if candidate in upper:
                    rating = candidate
                    break

        if not reasoning and rating in text.upper():
            remainder = text.upper().replace(rating, "", 1).strip(" -–—:")
            if remainder:
                reasoning = remainder

        return {"rating": rating, "reasoning": reasoning}

    @staticmethod
    def _parse_confidence(raw: str) -> dict[str, str]:
        text = raw.strip()
        if not text or text.upper() == "N/A":
            return {"level": "", "reason": ""}

        upper = text.upper()
        level = ""
        for candidate in ("HIGH", "MEDIUM", "LOW"):
            if candidate in upper:
                level = candidate
                break

        reason = text
        for sep in (" - ", " – ", " — "):
            if sep in text:
                reason = text.split(sep, 1)[1].strip()
                break
        if level and text.upper().startswith(level):
            reason = text[len(level) :].strip(" -–—:")

        return {"level": level, "reason": reason}

    @staticmethod
    def _investment_badge_kind(rating: str) -> str:
        normalized = rating.upper()
        if normalized == "BUY":
            return "up"
        if normalized == "AVOID":
            return "down"
        return "neutral"

    def _load_snapshot(self) -> dict[str, dict[str, Any]]:
        try:
            if self.snapshot_path.exists():
                with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if not isinstance(data, dict):
                        return {}
                    version = data.get("snapshot_version")
                    if version != SNAPSHOT_VERSION:
                        print(
                            f"ℹ️ Snapshot version mismatch ({version!r} != {SNAPSHOT_VERSION}) "
                            "— treating as baseline month"
                        )
                        return {}
                    companies = data.get("companies", {})
                    return companies if isinstance(companies, dict) else {}
        except Exception as exc:
            print(f"⚠️ Failed to load tech snapshot: {exc}")
        return {}

    def _save_snapshot(self, companies: dict[str, dict[str, Any]]) -> None:
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "snapshot_version": SNAPSHOT_VERSION,
                "companies": companies,
            }
            with open(self.snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(f"✓ Tech snapshot saved to {self.snapshot_path}")
        except Exception as exc:
            print(f"✗ Failed to save tech snapshot: {exc}")

    @staticmethod
    def _blank_insight() -> dict[str, str]:
        return {
            "sector_read": "",
            "investment_view": "",
            "confidence": "MEDIUM - No explicit confidence provided.",
            "expert_recommendation": "",
        }

    def _disabled_insight(self) -> dict[str, str]:
        return {
            "sector_read": "AI insights disabled - set OPENAI_API_KEY to enable.",
            "investment_view": "",
            "confidence": "N/A",
            "expert_recommendation": "",
        }

    def parse_structured_insights(
        self, response_text: str, technologies: list[str]
    ) -> dict[str, dict[str, str]]:
        results = {tech: self._blank_insight() for tech in technologies}
        if not response_text:
            return results

        tech_lookup = {tech.lower(): tech for tech in technologies}
        current_tech: str | None = technologies[0] if len(technologies) == 1 else None
        current_section: str | None = None
        section_buffer: list[str] = []
        saw_tech_header = False

        def flush() -> None:
            if current_tech and current_section and section_buffer:
                joined = " ".join(section_buffer).strip()
                if joined:
                    results[current_tech][current_section] = joined
                section_buffer.clear()

        for raw in response_text.splitlines():
            line = raw.strip()
            if not line:
                flush()
                continue
            upper = line.upper()

            if upper.startswith("TECHNOLOGY:"):
                flush()
                current_section = None
                saw_tech_header = True
                raw_name = line.split(":", 1)[1].strip().lower()
                current_tech = tech_lookup.get(raw_name)
                if not current_tech:
                    for low_name, canonical in tech_lookup.items():
                        if low_name in raw_name or raw_name in low_name:
                            current_tech = canonical
                            break
                continue

            if "SECTOR READ" in upper:
                flush()
                current_section = "sector_read"
                section_buffer = []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        section_buffer.append(content)
            elif "INVESTMENT VIEW" in upper:
                flush()
                current_section = "investment_view"
                section_buffer = []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        section_buffer.append(content)
            elif upper.startswith("CONFIDENCE"):
                flush()
                current_section = "confidence"
                section_buffer = []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        section_buffer.append(content)
            elif "EXPERT RECOMMENDATION" in upper:
                flush()
                current_section = None
                if current_tech and ":" in line:
                    value = line.split(":", 1)[1].strip()
                    if value:
                        results[current_tech]["expert_recommendation"] = value
            elif current_section and current_tech:
                section_buffer.append(line)

        flush()

        if len(technologies) == 1 and not saw_tech_header:
            single = results[technologies[0]]
            if not single["sector_read"] and not single["investment_view"]:
                single["sector_read"] = response_text[:500]

        return results

    def _build_batch_context(
        self,
        signals: dict[str, dict[str, Any]],
        category_summary: dict[str, dict[str, Any]],
    ) -> str:
        blocks: list[str] = [
            BATCH_TEMPLATE_HEADER,
            "",
            "CATEGORY MOMENTUM:",
            self._format_category_momentum(category_summary),
            "",
        ]
        for tech, signal in sorted(signals.items()):
            category = str(signal.get("category", "GeneralTech"))
            expert_type = self.get_category_expert(category)
            adopter_sectors = self.summarize_adopter_sectors(signal, self._company_sector_lookup)
            rising = ", ".join(signal.get("rising", [])) or "None"
            new = ", ".join(signal.get("new", [])) or "None"
            falling = ", ".join(signal.get("falling", [])) or "None"
            blocks.append(
                "\n".join(
                    [
                        f"TECHNOLOGY: {tech}",
                        f"CATEGORY: {category}",
                        f"SECTOR EXPERT: {expert_type}",
                        f"ADOPTER SECTORS: {adopter_sectors}",
                        f"RISING AT: {rising}",
                        f"NEW AT: {new}",
                        f"FALLING AT: {falling}",
                        f"AVG SHARE DELTA: {signal.get('avg_delta', 0.0)}",
                        f"MARKET-WIDE SIGNAL: {'YES' if signal.get('market_wide') else 'NO'}",
                        "",
                    ]
                )
            )
        return "\n".join(blocks)

    def _generate_single_ai_insight(self, tech: str, signal: dict[str, Any]) -> dict[str, str]:
        if not self.openai.is_enabled:
            return self._disabled_insight()

        category = str(signal.get("category", "GeneralTech"))
        context = SINGLE_TECHNOLOGY_TEMPLATE.format(
            technology=tech,
            category=category,
            expert_type=self.get_category_expert(category),
            adopter_sectors=self.summarize_adopter_sectors(signal, self._company_sector_lookup),
            rising=", ".join(signal.get("rising", [])) or "None",
            new=", ".join(signal.get("new", [])) or "None",
            falling=", ".join(signal.get("falling", [])) or "None",
            avg_delta=signal.get("avg_delta", 0.0),
            market_wide="YES" if signal.get("market_wide") else "NO",
        )
        try:
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=500,
            )
            return self.parse_structured_insights(content, [tech]).get(tech, self._blank_insight())
        except Exception as exc:
            return {
                "sector_read": f"AI insights unavailable: {exc}",
                "investment_view": "",
                "confidence": "N/A",
                "expert_recommendation": "",
            }

    def generate_batched_ai_insights(
        self,
        signals: dict[str, dict[str, Any]],
        category_summary: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        technologies = sorted(signals.keys())
        if not technologies:
            return {}
        if not self.openai.is_enabled:
            return {tech: self._disabled_insight() for tech in technologies}

        def primary() -> dict[str, dict[str, str]]:
            context = self._build_batch_context(signals, category_summary)
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=500 * max(1, min(len(technologies), 8)),
            )
            return self.parse_structured_insights(content, technologies)

        def fallback() -> dict[str, dict[str, str]]:
            return {
                tech: self._generate_single_ai_insight(tech, signals[tech]) for tech in technologies
            }

        return self.openai.run_with_fallback(primary, fallback)

    def generate_market_overview(
        self,
        signals: dict[str, dict[str, Any]],
        category_summary: dict[str, dict[str, Any]],
    ) -> str:
        if not self.openai.is_enabled or not signals:
            return ""

        ordered = sorted(
            signals.items(),
            key=lambda item: (item[1].get("market_wide", False), item[1].get("avg_delta", 0.0)),
            reverse=True,
        )[:5]
        top_signal_lines = [
            (
                f"- {tech} ({signal.get('category', 'GeneralTech')}): "
                f"avg delta {signal.get('avg_delta', 0.0)} pts, "
                f"market-wide={'yes' if signal.get('market_wide') else 'no'}"
            )
            for tech, signal in ordered
        ]
        context = MARKET_OVERVIEW_TEMPLATE.format(
            category_summary=self._format_category_momentum(category_summary),
            top_signals="\n".join(top_signal_lines) or "No top signals",
        )
        try:
            return self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=200,
            ).strip()
        except Exception as exc:
            print(f"⚠️ Market overview generation failed: {exc}")
            return ""

    def create_digest_email(
        self,
        signals: dict[str, dict[str, Any]],
        insights: dict[str, dict[str, str]],
        market_overview: str = "",
    ) -> tuple[str, str, str]:
        n = len(signals)
        subject = f"Monthly tech trends — {n} signal{'s' if n != 1 else ''}"

        ordered = sorted(
            signals.items(),
            key=lambda item: (item[1].get("market_wide", False), item[1].get("avg_delta", 0.0)),
            reverse=True,
        )
        category_summary = self.summarize_category_momentum(signals)
        shown = min(n, 8)

        html_cards: list[str] = []
        plain_blocks: list[str] = []

        for tech, signal in ordered[:shown]:
            insight = insights.get(tech, self._blank_insight())
            category = str(signal.get("category", "GeneralTech"))
            category_label = self.get_category_display_name(category)

            parsed_view = self._parse_investment_view(insight.get("investment_view", ""))
            parsed_confidence = self._parse_confidence(insight.get("confidence", ""))
            expert = insight.get("expert_recommendation") or self.get_category_expert(category)

            meta_chips = et.stat_chip("Category", category_label, "neutral")
            if signal.get("market_wide"):
                meta_chips += et.stat_chip("Market-wide", "Yes", "up")
            meta_chips += et.stat_chip(
                "Avg delta",
                f"{signal.get('avg_delta', 0.0)} pts",
                "up" if float(signal.get("avg_delta", 0.0) or 0.0) > 0 else "neutral",
            )

            adoption_parts: list[str] = []
            rising = signal.get("rising", [])
            new = signal.get("new", [])
            falling = signal.get("falling", [])
            if rising:
                adoption_parts.append(
                    et.badge_row("Rising", "".join(et.badge(company, "up") for company in rising))
                )
            if new:
                adoption_parts.append(
                    et.badge_row("New", "".join(et.badge(company, "up") for company in new))
                )
            if falling:
                adoption_parts.append(
                    et.badge_row(
                        "Falling", "".join(et.badge(company, "down") for company in falling)
                    )
                )

            card_body = (
                f'<div style="font-size:13px;color:{et.MUTED};margin:0 0 14px 0;">{meta_chips}</div>'
                + "".join(adoption_parts)
            )
            if adoption_parts:
                card_body += et.divider()
            card_body += et.verdict_block(
                rating=parsed_view["rating"],
                confidence=parsed_confidence["level"],
                expert=expert,
                conclusion=parsed_view["reasoning"],
                reasoning=parsed_confidence["reason"],
                badge_kind=self._investment_badge_kind(parsed_view["rating"]),
            )

            sector_read = insight.get("sector_read", "")
            if sector_read and self._is_meaningful_insight(sector_read):
                card_body += et.callout(et.section("Sector Read", sector_read))

            html_cards.append(et.card(card_body, title=tech))

            plain_blocks.append(
                "\n".join(
                    [
                        f"{tech} ({category_label})",
                        f"  Rising: {', '.join(rising) or 'None'}",
                        f"  New: {', '.join(new) or 'None'}",
                        f"  Falling: {', '.join(falling) or 'None'}",
                        f"  Investment view: {insight.get('investment_view', 'WATCH')}",
                        f"  Sector read: {sector_read}",
                        f"  Expert: {expert}",
                        f"  Confidence: {insight.get('confidence', 'N/A')}",
                    ]
                )
            )

        category_rows: list[str] = []
        category_plain: list[str] = []
        sorted_categories = sorted(category_summary.items())
        for index, (category, bucket) in enumerate(sorted_categories):
            display_name = self.get_category_display_name(category)
            row = et.momentum_row(
                display_name,
                bucket["rising"],
                bucket["new"],
                bucket["falling"],
                bucket["market_wide"],
                show_border=index < len(sorted_categories) - 1,
            )
            category_rows.append(row)
            category_plain.append(
                f"{display_name}: {bucket['rising']} rising, {bucket['new']} new, "
                f"{bucket['falling']} falling, {bucket['market_wide']} market-wide"
            )

        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header_subtitle = (
            f"{n} signal{'s' if n != 1 else ''} · "
            f"{len(category_summary)} categor{'ies' if len(category_summary) != 1 else 'y'} · "
            "monthly digest"
        )
        blocks: list[str] = [
            et.header("Monthly Tech Trends", header_subtitle),
        ]
        if market_overview:
            blocks.append(et.overview_block("This Month at a Glance", et.esc(market_overview)))
        if category_rows:
            blocks.append(et.card("".join(category_rows), title="Category Momentum"))
        blocks.append(et.section_heading(f"Top Signals ({shown} of {n})"))
        blocks.extend(html_cards)

        footer_text = f"Generated on {generated}"
        if n > shown:
            footer_text += f" · Showing top {shown} of {n} signals by momentum"
        blocks.append(et.footer(footer_text))

        html_content = et.page("Monthly Tech Trends", blocks)
        plain_content = (
            "MONTHLY TECH TRENDS\n"
            "===================\n\n"
            + header_subtitle
            + "\n\n"
            + (f"THIS MONTH AT A GLANCE\n{market_overview}\n\n" if market_overview else "")
            + "CATEGORY MOMENTUM\n"
            + "-----------------\n"
            + ("\n".join(category_plain) if category_plain else "No category momentum detected.")
            + "\n\n"
            + f"TOP SIGNALS ({shown} of {n})\n"
            + "--------------------\n"
            + "\n\n".join(plain_blocks)
            + f"\n\n{footer_text}\n"
        )
        return subject, html_content, plain_content

    def run(self, test_mode: bool = False) -> None:
        print("🚀 Starting Techstack Agent")
        if test_mode:
            print("🧪 TEST_MODE on")

        if not self.client:
            print("❌ ADZUNA_APP_ID/ADZUNA_APP_KEY not set. Exiting.")
            return

        companies = load_companies(self.settings.techstack_watchlist_csv)
        if not companies:
            print("❌ No companies loaded. Exiting.")
            return

        previous = self._load_snapshot()
        current: dict[str, dict[str, Any]] = {}
        company_trends: list[dict[str, Any]] = []
        max_days_old = self.lookback_days
        print(f"📅 Using {max_days_old}-day job posting lookback")

        for idx, company in enumerate(companies, 1):
            name = company["company"]
            query = company["search_query"]
            print(f"--- Processing {name} ({idx}/{len(companies)}) ---")
            postings = self.client.get_job_postings(query=query, max_days_old=max_days_old)
            if not postings:
                print("  (no postings found)")
                continue

            counts, total = self.extract_tech_mentions(postings)
            current[name] = {
                "technologies": counts,
                "total": total,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            trends = self.detect_company_trends(
                company=company,
                current_counts=counts,
                current_total=total,
                previous_entry=previous.get(name),
            )
            company_trends.extend(trends)
            if trends:
                print(f"  🔔 Detected {len(trends)} trend(s)")

        for name, entry in previous.items():
            current.setdefault(name, entry)
        self._save_snapshot(current)

        if not company_trends:
            print("✅ No meaningful techstack trends detected. Nothing to send.")
            return

        signals = self.detect_cross_company_trends(company_trends)
        self._company_sector_lookup = self.build_company_sector_lookup(companies)
        category_summary = self.summarize_category_momentum(signals)
        market_overview = self.generate_market_overview(signals, category_summary)
        insights = self.generate_batched_ai_insights(signals, category_summary)
        subject, html_content, plain_content = self.create_digest_email(
            signals, insights, market_overview=market_overview
        )
        if self.email_sender.send(subject, html_content, plain_content):
            print(f"🎉 Sent 1 digest email covering {len(signals)} technology trend(s)")
        else:
            print("✗ Failed to send digest email")

