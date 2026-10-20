"""CV Enhancer - AWS architecture diagram (official AWS icons).

Generates 'cv-enhancer-architecture.png' using the `diagrams` library, which
bundles the official AWS Architecture Icon set.

Prerequisites:
    1. Install Graphviz (the `dot` binary must be on PATH):
         - Windows:  winget install graphviz   (or  choco install graphviz)
         - macOS:    brew install graphviz
         - Linux:    sudo apt-get install graphviz
    2. pip install -r requirements.txt

Run:
    python architecture.py
"""
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.integration import SimpleQueueServiceSqs, SimpleNotificationServiceSns
from diagrams.aws.compute import Lambda
from diagrams.aws.ml import Bedrock
from diagrams.aws.storage import SimpleStorageServiceS3
from diagrams.aws.network import APIGateway
from diagrams.aws.security import WAF
from diagrams.aws.management import Cloudwatch
from diagrams.onprem.client import User

graph_attr = {
    "fontsize": "20",
    "labelloc": "t",
    "pad": "0.6",
    "splines": "spline",
    "bgcolor": "white",
}

with Diagram(
    "CV Enhancer - AWS Architecture",
    filename="cv-enhancer-architecture",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
):
    user = User("User\n(Browser SPA)")

    with Cluster("AWS Cloud - us-east-1"):
        waf = WAF("AWS WAF\nIP rate limit")
        api = APIGateway("API Gateway\nPOST /analyze-cv")

        with Cluster("Async processing"):
            queue = SimpleQueueServiceSqs("SQS\nJob Queue")
            worker = Lambda("Worker Lambda")
            dlq = SimpleQueueServiceSqs("SQS\nDead-letter Queue")

        bedrock = Bedrock("Bedrock\nAnalyze + Enhance")
        results = SimpleStorageServiceS3("S3 (private)\nEnhanced CV + Analysis")
        topic = SimpleNotificationServiceSns("SNS\nNotifications")

        logs = Cloudwatch("CloudWatch\nLogs + X-Ray")

        # Main request flow
        user >> Edge(label="1. CV + job details") >> waf
        waf >> Edge(label="rate-limited") >> api
        api >> Edge(label="2. SendMessage") >> queue
        queue >> Edge(label="3. trigger") >> worker
        worker >> Edge(label="4. enhance") >> bedrock
        worker >> Edge(label="5. save results") >> results
        worker >> Edge(label="6. publish") >> topic
        topic >> Edge(label="7. email: secure link", style="dashed") >> user

        # Failure path
        queue >> Edge(label="after 3 retries", style="dashed", color="firebrick") >> dlq

        # Observability
        worker >> Edge(style="dotted", color="gray", label="logs") >> logs
