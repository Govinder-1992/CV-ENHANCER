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
from diagrams.onprem.client import User, Client
from diagrams.onprem.vcs import Github

graph_attr = {
    "fontsize": "20",
    "labelloc": "t",
    "pad": "0.7",
    "nodesep": "0.8",
    "ranksep": "1.1",
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
    user = User("User")

    with Cluster("Local machine"):
        spa = Client("Frontend SPA\n(run locally)")

    with Cluster("CI/CD"):
        gh = Github("GitHub Actions\n(SAM deploy)")

    with Cluster("AWS Cloud - us-east-1"):
        with Cluster("Edge / API"):
            waf = WAF("AWS WAF\nIP rate limit")
            api = APIGateway("API Gateway\nPOST /analyze-cv")

        with Cluster("Async processing"):
            queue = SimpleQueueServiceSqs("SQS\nJob Queue")
            worker = Lambda("Worker Lambda")
            dlq = SimpleQueueServiceSqs("SQS\nDead-letter Queue")

        with Cluster("AI + storage + notify"):
            bedrock = Bedrock("Bedrock\nAnalyze + Enhance")
            results = SimpleStorageServiceS3("S3 (private)\nEnhanced CV + Analysis")
            topic = SimpleNotificationServiceSns("SNS\nNotifications")

        logs = Cloudwatch("CloudWatch\nLogs + X-Ray")

        # Request flow
        user >> Edge(label="1. open") >> spa
        spa >> Edge(label="2. submit CV + job details") >> waf
        waf >> Edge(label="rate-limited") >> api
        api >> Edge(label="3. SendMessage") >> queue
        queue >> Edge(label="4. trigger") >> worker
        worker >> Edge(label="5. enhance") >> bedrock
        worker >> Edge(label="6. save results") >> results
        worker >> Edge(label="7. publish") >> topic
        topic >> Edge(label="8. email: secure link", style="dashed") >> user

        # Failure path + observability
        queue >> Edge(label="after 3 retries", style="dashed", color="firebrick") >> dlq
        worker >> Edge(style="dotted", color="gray", label="logs") >> logs

    # CI/CD deploys the backend stack
    gh >> Edge(style="dotted", color="darkgreen", label="deploy") >> api
