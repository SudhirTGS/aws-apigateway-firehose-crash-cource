# AWS API Gateway + Kinesis Firehose + Lambda Transform Pipeline

## Overview
This project demonstrates a serverless data ingestion pipeline on AWS using API Gateway, Kinesis Firehose, Lambda transformation, and delivery to New Relic with S3 backup.

---

## Architecture

```
API Gateway (REST API)
    ↓ PutRecord
Kinesis Firehose (Buffer: 1 MB / 60 sec)
    ↓ Invoke
Lambda Transform (Python 3.9)
    ↓ Mixed result: "Ok" / "ProcessingFailed"
    ├─→ "Ok" records → New Relic HTTP Endpoint
    │                   ↓ (on failure)
    │                   S3 Backup Bucket
    │
    └─→ "ProcessingFailed" records → S3 Backup Bucket (immediate)
```

---

## Key Components

### 1. API Gateway
- **Endpoint**: `POST /prod/`
- **Integration**: Direct PutRecord to Kinesis Firehose
- **Payload**: JSON messages (automatically base64-encoded by Firehose)

### 2. Kinesis Firehose Delivery Stream
- **Buffering**: 1 MB or 60 seconds (whichever comes first)
- **Transform**: Lambda function (`firehose-transform-handler`)
- **Destination**: New Relic HTTP endpoint (`log-api.newrelic.com/log/v1`)
- **Backup**: S3 bucket for failed/all records
- **Retry**: 60 seconds for HTTP failures, 3 retries for Lambda failures

### 3. Lambda Transform Function
- **Runtime**: Python 3.9
- **Handler**: `lambda_firehose_handler.lambda_handler`
- **Contract**: AWS Firehose Transform API
  ```python
  {
    "records": [
      {
        "recordId": "string",              # Must match input
        "result": "Ok" | "ProcessingFailed" | "Dropped",  # AWS-required
        "data": "BASE64"                   # Transformed or original data
      }
    ]
  }
  ```

- **Transformation Logic**:
  - Decodes base64 → parses JSON (or wraps plain text)
  - Adds metadata: `transformed: true`, `_transformed_ts: timestamp`
  - Re-encodes to base64
  - Returns `result: "Ok"` on success, `"ProcessingFailed"` on error

### 4. S3 Backup Bucket
- **Purpose**: Durability for failed records
- **Contents**:
  - Records that failed Lambda processing (`ProcessingFailed`)
  - Records that failed HTTP delivery (after 60 sec retry)
- **Format**: Base64-encoded records (one per line)
- **Retention**: Permanent (configure lifecycle rules as needed)

---

## Data Flow

### Normal Flow (Success)
```
1. API Gateway receives JSON → PutRecord to Firehose
2. Firehose buffers records (1 MB / 60 sec)
3. Lambda transforms batch → returns all "Ok"
4. Firehose sends to New Relic → HTTP 200 ✓
5. Done
```

### Failure Scenarios

#### Lambda Processing Failure
```
1-2. [Same as above]
3. Lambda fails for record X → returns "ProcessingFailed" for X, "Ok" for others
4. Firehose:
   - Writes record X to S3 backup immediately
   - Sends "Ok" records to New Relic
```

#### HTTP Delivery Failure
```
1-3. [Same as success flow]
4. New Relic returns HTTP 500 → Retry for 60 seconds
5. Still failing → All records written to S3 backup
```

#### Both Failures (Rare)
```
HTTP fails → S3 backup also fails
→ Firehose holds records for ~24 hours (transient retry buffer)
→ After 24 hours → PERMANENT DATA LOSS
```

---

## AWS Firehose Transform API Contract

### Required Response Format
- **Mandatory Fields**:
  - `recordId`: Must match input recordId
  - `result`: Must be `"Ok"`, `"ProcessingFailed"`, or `"Dropped"`
  - `data`: Base64-encoded transformed data

### Valid `result` Values

| Value | Meaning | Firehose Behavior |
|-------|---------|-------------------|
| `"Ok"` | Processing succeeded | Deliver to destination (HTTP/S3) |
| `"ProcessingFailed"` | Processing failed (retryable) | Skip destination, write to S3 backup, retry Lambda |
| `"Dropped"` | Intentionally discarded | Do not deliver anywhere |

### Contract Validation
- Firehose validates **every field** in the Lambda response
- Invalid/missing fields → treated as Lambda invocation error
- Lambda retries (up to 3 times per config)
- After retries → entire batch to S3 backup

---

## Deployment

### Prerequisites
- AWS CLI configured
- Terraform installed
- Python 3.9+
- AWS account with appropriate permissions

### Steps
```bash
# 1. Package Lambda function
zip lambda_firehose_handler.zip lambda_firehose_handler.py

# 2. Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply

# 3. Get outputs
terraform output

# 4. Test the pipeline
API_ENDPOINT=$(terraform output -raw api_invoke_url)
curl -X POST $API_ENDPOINT \
  -H "Content-Type: application/json" \
  -d '{"test": "data", "timestamp": "2026-02-05"}'

# 5. Verify delivery
# Check New Relic logs
# Check S3 backup bucket (should be empty if successful)
aws s3 ls s3://$(terraform output -raw firehose_bucket_name)/ --recursive
```

---

## Monitoring

### CloudWatch Metrics

| Metric | What to Monitor |
|--------|-----------------|
| `IncomingRecords` | Total records sent to Firehose |
| `DeliveryToHttpEndpoint.Success` | HTTP delivery success rate |
| `DeliveryToHttpEndpoint.DataFreshness` | Delivery lag (high = retries/failures) |
| `DeliveryToS3.Records` | Records written to S3 backup (should be low) |
| `ExecuteProcessing.Success` | Lambda invocation success rate |
| `ExecuteProcessing.Duration` | Lambda execution time |

### Recommended Alarms
```terraform
# Example: Alert on high S3 backup writes
resource "aws_cloudwatch_metric_alarm" "high_s3_backup" {
  alarm_name          = "firehose-high-s3-backup"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DeliveryToS3.Records"
  namespace           = "AWS/Firehose"
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  alarm_description   = "Too many records going to S3 backup"
  
  dimensions = {
    DeliveryStreamName = aws_kinesis_firehose_delivery_stream.my_first_stream.name
  }
}
```

---

## Key Concepts

### Firehose vs Kinesis Data Streams

| Feature | Kinesis Firehose | Kinesis Data Streams |
|---------|------------------|----------------------|
| **Purpose** | Delivery/ingestion pipeline | Durable event stream |
| **Retention** | ~24 hours (transient retry buffer) | 24 hours default, up to 365 days |
| **Durability** | Low (use S3 backup) | High (replicated across AZs) |
| **Consumers** | Single destination | Multiple (Flink, Lambda, custom) |
| **Use case** | ETL, log aggregation, analytics ingestion | Event sourcing, stream processing |

### 24-Hour Retention Window
- **Not configurable** — AWS service limit
- **Purpose**: Transient buffer for records that fail delivery (both HTTP and S3 backup)
- **Countdown**: Starts when HTTP fails AND S3 backup fails
- **Outcome**: After 24 hours, records are dropped permanently
- **Prevention**: Always configure S3 backup (your config already has this ✓)

### Per-Record vs Batch-Level Failures

| Failure Location | Single Record Behavior | Other Records in Batch |
|------------------|------------------------|------------------------|
| **Lambda processing** | Marked `ProcessingFailed` → goes to S3 | Continue to HTTP endpoint |
| **HTTP endpoint** | Not possible (batch-level response) | Entire batch fails together |

---

## Best Practices

### ✅ Do
- Always configure S3 backup (`s3_configuration`)
- Monitor CloudWatch metrics and set alarms
- Follow AWS Firehose Transform API contract exactly
- Log Lambda processing stats (success/failed counts)
- Test failure paths regularly (disable HTTP endpoint, inject Lambda errors)
- Add metadata to records for traceability (`_record_id`, `_processing_status`)
- Use S3 lifecycle rules to expire old backups

### ❌ Don't
- Rely on 24-hour retention window for durability (use S3 backup)
- Invent custom field names in Lambda response (use `result`, not `status`)
- Skip records in Lambda output (must return one output per input)
- Ignore CloudWatch alarms (high `DeliveryToS3.Records` = problem)

---

## Troubleshooting

### Issue: Records Going to S3 Backup
**Check**:
1. New Relic HTTP endpoint status (API key valid? Rate limits?)
2. Lambda logs for `ProcessingFailed` errors
3. CloudWatch metric `DeliveryToHttpEndpoint.Success` (should be near 100%)

**Fix**:
- Verify New Relic API key in Terraform config
- Check Lambda execution role permissions
- Increase `retry_duration` if New Relic has transient issues

### Issue: Lambda Invocation Errors
**Check**:
1. Lambda response format (must follow AWS contract)
2. CloudWatch Logs for validation errors
3. Metric `ExecuteProcessing.Success` (should be near 100%)

**Fix**:
- Validate Lambda response structure locally
- Ensure `recordId`, `result`, `data` fields are present and valid
- Check base64 encoding correctness

### Issue: High Latency
**Check**:
1. Metric `DeliveryToHttpEndpoint.DataFreshness` (should be < 120 sec)
2. Lambda duration (should be < 1000 ms for most workloads)
3. Buffer settings (1 MB / 60 sec may cause delays)

**Fix**:
- Optimize Lambda transformation logic
- Consider decreasing `buffering_interval` (minimum 60 sec for HTTP)
- Scale Lambda concurrency if needed

---

## Recovery from S3 Backup

### Option 1: Replay to Firehose
```bash
# Download backup files
aws s3 cp s3://bucket/path/to/backup ./backup.txt

# Parse and re-send (each line is base64-encoded record)
# Decode, validate, and POST to API Gateway or use PutRecordBatch
```

### Option 2: Direct Processing
```python
import boto3
import base64
import json

s3 = boto3.client('s3')

# List backup files
response = s3.list_objects_v2(Bucket='bucket', Prefix='2026/02/05/')

for obj in response.get('Contents', []):
    file_obj = s3.get_object(Bucket='bucket', Key=obj['Key'])
    content = file_obj['Body'].read().decode('utf-8')
    
    for line in content.strip().split('\n'):
        if line:
            decoded = base64.b64decode(line).decode('utf-8')
            record = json.loads(decoded)
            # Process or re-send to New Relic
```

---

## Cost Optimization

### Firehose Pricing
- **Data ingestion**: $0.029 per GB
- **Data format conversion**: $0.018 per GB (not used in this config)
- **VPC delivery**: Additional charges (not used)

### Lambda Pricing
- **Requests**: $0.20 per 1M requests
- **Duration**: $0.0000166667 per GB-second

### S3 Pricing
- **Storage**: $0.023 per GB/month (Standard)
- **PUT requests**: $0.005 per 1,000 requests

### Optimization Tips
- Set S3 lifecycle rules to delete old backups (e.g., 30 days)
- Monitor Lambda duration and optimize transformation logic
- Use `s3_backup_mode = "FailedDataOnly"` (default) instead of `"AllData"`

---

## Project Structure

```
.
├── lambda_firehose_handler.py    # Lambda transform function
├── lambda_firehose_handler.zip   # Packaged Lambda (generated)
├── terraform/
│   └── main.tf                   # Terraform infrastructure
├── README.md                     # This file
└── .gitignore
```

---

## Related AWS Services

### Alternatives for Different Use Cases
- **MSK (Managed Kafka)**: When you need durable streams, multiple consumers, strict ordering
- **Kinesis Data Streams**: When you need replay, long retention, or custom stream processing
- **EventBridge**: When you need event routing, filtering, and multi-target fanout
- **SQS**: When you need simple message queuing without streaming semantics

---

## References

- [AWS Kinesis Firehose Documentation](https://docs.aws.amazon.com/firehose/latest/dev/what-is-this-service.html)
- [Firehose Lambda Transform API](https://docs.aws.amazon.com/firehose/latest/dev/data-transformation.html)
- [Lambda Blueprints for Firehose](https://docs.aws.amazon.com/firehose/latest/dev/lambda-blueprints.html)
- [New Relic Log API](https://docs.newrelic.com/docs/logs/log-api/introduction-log-api/)

---

## License
MIT

---

## Contributing
Pull requests welcome. For major changes, please open an issue first to discuss what you would like to change.
