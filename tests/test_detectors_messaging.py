import pytest

from stackatlas.config import Config
from stackatlas.detectors import detect, messaging
from stackatlas.detectors.messaging import messaging_name


def _refs(tmp_path, files):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    refs = detect("app", tmp_path, Config(), [messaging])
    return [(r.path, r.line, r.kind, r.value, r.role, r.engine, r.key, r.env) for r in refs]


def test_jms_listener_and_template_with_value_fields(tmp_path):
    java = (
        "class A {\n"
        '    @Value("${aws.sqs.outQueue}")\n'
        "    private String outQueue;\n"
        "\n"
        '    @JmsListener(destination = "${aws.sqs.inQueue}", containerFactory = "f")\n'
        "    public void on(String m) {\n"
        "        jmsTemplate.convertAndSend(outQueue, m);\n"
        '        this.jmsTemplate.send("literal-queue", creator);\n'
        "        jmsTemplate.convertAndSend(unknownParam, m);\n"
        "    }\n"
        "}\n"
    )
    assert _refs(tmp_path, {"src/A.java": java}) == [
        ("src/A.java", 5, "var", "aws.sqs.inQueue", "consume", "queue", None, None),
        ("src/A.java", 7, "var", "aws.sqs.outQueue", "produce", "queue", None, None),
        ("src/A.java", 8, "name", "literal-queue", "produce", "queue", None, None),
    ]


def test_sqs_and_sns_sdk_builders(tmp_path):
    java = (
        "class B {\n"
        "    @Value(\"${aws.sqs.workQueueUrl}\") private String workQueueUrl;\n"
        "    @Value(\"${privacyTopicArn}\")\n"
        "    private final String topicArn;\n"
        "    void send() {\n"
        "        sqsClient.sendMessage(SendMessageRequest.builder()\n"
        "            .queueUrl(workQueueUrl)\n"
        "            .messageBody(b).build());\n"
        "    }\n"
        "    void poll() {\n"
        "        ReceiveMessageRequest r = ReceiveMessageRequest.builder()\n"
        "            .queueUrl(workQueueUrl).build();\n"
        "    }\n"
        "    void pub() {\n"
        "        PublishRequest request = PublishRequest.builder()\n"
        "            .topicArn(topicArn).message(m).build();\n"
        "        snsClient.publish(request);\n"
        "    }\n"
        "}\n"
    )
    assert _refs(tmp_path, {"B.java": java}) == [
        ("B.java", 7, "var", "aws.sqs.workQueueUrl", "produce", "queue", None, None),
        ("B.java", 12, "var", "aws.sqs.workQueueUrl", "consume", "queue", None, None),
        ("B.java", 16, "var", "privacyTopicArn", "produce", "topic", None, None),
    ]


def test_sqs_listener_kafka_and_rabbit(tmp_path):
    java = (
        "class C {\n"
        '    @SqsListener(value = "${aws.sqs.load}", factory = "x")\n'
        "    void a() {}\n"
        '    @SqsListener("plain-queue")\n'
        "    void b() {}\n"
        '    @KafkaListener(topics = {"inventory-updates"}, groupId = "g")\n'
        "    void c() {}\n"
        '    @RabbitListener(queues = "${rabbit.audit.queue}")\n'
        "    void d() {\n"
        '        kafkaTemplate.send("price-changes", m);\n'
        '        rabbitTemplate.convertAndSend("audit-out", m);\n'
        "    }\n"
        "}\n"
    )
    assert _refs(tmp_path, {"C.kt": java}) == [
        ("C.kt", 2, "var", "aws.sqs.load", "consume", "queue", None, None),
        ("C.kt", 4, "name", "plain-queue", "consume", "queue", None, None),
        ("C.kt", 6, "name", "inventory-updates", "consume", "topic", None, None),
        ("C.kt", 8, "var", "rabbit.audit.queue", "consume", "queue", None, None),
        ("C.kt", 10, "name", "price-changes", "produce", "topic", None, None),
        ("C.kt", 11, "name", "audit-out", "produce", "queue", None, None),
    ]


def test_python_boto3_calls(tmp_path):
    py = (
        "import os\n"
        "QUEUE = os.environ['TARGET_SQS_URL']\n"
        "TOPIC = os.getenv(\"ALERTS_TOPIC_ARN\")\n"
        "def h(e, c):\n"
        "    sqs.send_message_batch(QueueUrl=QUEUE, Entries=[])\n"
        "    sns.publish(TopicArn=TOPIC, Message='x')\n"
        "    sns.publish(\n"
        "        TopicArn=os.environ.get('OTHER_TOPIC'), Message='y')\n"
        "    sqs.receive_message(QueueUrl=QUEUE)\n"
        "    sqs.send_message(QueueUrl=local_name)\n"
    )
    assert _refs(tmp_path, {"src/h.py": py}) == [
        ("src/h.py", 5, "var", "TARGET_SQS_URL", "produce", "queue", None, None),
        ("src/h.py", 6, "var", "ALERTS_TOPIC_ARN", "produce", "topic", None, None),
        ("src/h.py", 7, "var", "OTHER_TOPIC", "produce", "topic", None, None),
        ("src/h.py", 9, "var", "TARGET_SQS_URL", "consume", "queue", None, None),
    ]


def test_config_values_are_value_only_refs(tmp_path):
    files = {
        "src/main/resources/application-dev.properties": (
            "aws.sqs.inQueue=dev-orders-in\n"
            "event.broadcast.queue.capacity=100\n"
            "aws.sqs.enabled=true\n"
            "aws.sqs.activity=${SQS_ACTIVITY_QUEUE:dev-activity}\n"
            "aws.sqs.fromEnv=${SQS_ONLY}\n"
            "sqs.secret.key=abc\n"
        ),
        ".env.production": (
            "ALERTS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:prod-alerts\nPORT=80\n"
        ),
    }
    got = _refs(tmp_path, files)
    props = "src/main/resources/application-dev.properties"
    assert got == [
        (".env.production", 1, "name", "arn:aws:sns:us-east-1:123456789012:prod-alerts", None,
         None, "ALERTS_TOPIC_ARN", "prod"),
        (props, 1, "name", "dev-orders-in", None, None, "aws.sqs.inQueue", "dev"),
        (props, 4, "name", "dev-activity", None, None, "aws.sqs.activity", "dev"),
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("arn:aws:sqs:us-east-1:123456789012:prod-orders.fifo", ("queue", "prod-orders.fifo")),
        ("arn:aws:sns:::*-alerts", ("topic", "alerts")),
        ("https://sqs.us-east-1.amazonaws.com/123456789012/dev-work", ("queue", "dev-work")),
        ("dev-customer-change.fifo", (None, "dev-customer-change.fifo")),
        ("*-customer-change.fifo", (None, "customer-change.fifo")),
        ("${var.x}", None),
        ("https://api.acme.com/v1", None),
        ("100", None),
        ("true", None),
    ],
)
def test_messaging_name(value, expected):
    assert messaging_name(value) == expected
