provider "aws" {
  region = "us-east-1"
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "firehose_bucket" {
  bucket        = "my-firehose-demo-bucket-${random_id.suffix.hex}"
  force_destroy = true
  tags = {
    Name    = "FirehoseDemoBucket"
    Purpose = "Learning"
  }
}

# Package the Lambda from the repository
# Using an already-created zip file: ensure lambda_firehose_handler.zip is present in this module directory

# IAM role for Lambda execution
resource "aws_iam_role" "lambda_role" {
  name = "firehose_transform_lambda_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = { Service = "lambda.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic_exec" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda function used as Firehose processor
resource "aws_lambda_function" "firehose_handler" {
  filename         = "${path.module}/../lambda_firehose_handler.zip"
  function_name    = "firehose-transform-handler"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_firehose_handler.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = filebase64sha256("${path.module}/../lambda_firehose_handler.zip")
}

# Allow Firehose to invoke the Lambda
resource "aws_lambda_permission" "allow_firehose_invoke" {
  statement_id  = "AllowFirehoseInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.firehose_handler.function_name
  principal     = "firehose.amazonaws.com"
}

# IAM role that Firehose will assume (write to S3 and invoke Lambda)
resource "aws_iam_role" "firehose_role" {
  name = "firehose_delivery_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = { Service = "firehose.amazonaws.com" },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "firehose_policy" {
  name = "firehose_delivery_policy"
  role = aws_iam_role.firehose_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ],
        Resource = [
          aws_s3_bucket.firehose_bucket.arn,
          "${aws_s3_bucket.firehose_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = ["lambda:InvokeFunction"],
        Resource = [aws_lambda_function.firehose_handler.arn]
      },
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

# Kinesis Firehose delivery stream sending to New Relic HTTP endpoint with S3 backup
resource "aws_kinesis_firehose_delivery_stream" "my_first_stream" {
  name        = "my-first-stream"
  destination = "http_endpoint"

  http_endpoint_configuration {
    url                = "https://log-api.newrelic.com/log/v1"
    name               = "newrelic-endpoint"
    access_key         = "4f209aa9bf056bceed54d8f482c09aefFFFFNRAL"
    role_arn           = aws_iam_role.firehose_role.arn
    buffering_size     = 1
    buffering_interval = 60

    request_configuration {
      content_encoding = "GZIP"
    }

    retry_duration = 60

    s3_configuration {
      role_arn           = aws_iam_role.firehose_role.arn
      bucket_arn         = aws_s3_bucket.firehose_bucket.arn
      buffering_size     = 1
      buffering_interval = 60
      compression_format = "UNCOMPRESSED"
    }

    # Optional: processing configuration to invoke Lambda for record transformation
    processing_configuration {
      enabled = true

      processors {
        type = "Lambda"

        parameters {
          parameter_name  = "LambdaArn"
          parameter_value = aws_lambda_function.firehose_handler.arn
        }

        parameters {
          parameter_name  = "NumberOfRetries"
          parameter_value = "3"
        }
      }
    }
  }

  tags = { Purpose = "Learning" }
}

# API Gateway role to call Firehose PutRecord
resource "aws_iam_role" "apigateway_role" {
  name = "apigateway_call_firehose_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = { Service = "apigateway.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy" "apigw_firehose_policy" {
  name = "apigw_firehose_policy"
  role = aws_iam_role.apigateway_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["firehose:PutRecord","firehose:PutRecordBatch"],
        Resource = [aws_kinesis_firehose_delivery_stream.my_first_stream.arn]
      }
    ]
  })
}

# API Gateway REST API
resource "aws_api_gateway_rest_api" "api" {
  name = "senddatatofirehose"
}

resource "aws_api_gateway_method" "post" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  resource_id   = aws_api_gateway_rest_api.api.root_resource_id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "firehose_integration" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_rest_api.api.root_resource_id
  http_method             = aws_api_gateway_method.post.http_method
  integration_http_method = "POST"
  type                    = "AWS"
  uri                     = "arn:aws:apigateway:us-east-1:firehose:action/PutRecord"
  credentials             = aws_iam_role.apigateway_role.arn
  passthrough_behavior    = "WHEN_NO_MATCH"

  request_templates = {
    "application/json" = <<EOF
{"DeliveryStreamName":"${aws_kinesis_firehose_delivery_stream.my_first_stream.name}","Record":{"Data":"$util.base64Encode($input.body)"}}
EOF
  }
}

resource "aws_api_gateway_method_response" "method_response_200" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_rest_api.api.root_resource_id
  http_method = aws_api_gateway_method.post.http_method
  status_code = "200"
}

resource "aws_api_gateway_deployment" "deployment" {
  depends_on = [aws_api_gateway_integration.firehose_integration]
  rest_api_id = aws_api_gateway_rest_api.api.id
}

resource "aws_api_gateway_stage" "prod" {
  deployment_id = aws_api_gateway_deployment.deployment.id
  rest_api_id   = aws_api_gateway_rest_api.api.id
  stage_name    = "prod"
}

output "firehose_stream_name" {
  value = aws_kinesis_firehose_delivery_stream.my_first_stream.name
}

output "firehose_bucket_name" {
  value = aws_s3_bucket.firehose_bucket.bucket
}

output "api_invoke_url" {
  value = "https://${aws_api_gateway_rest_api.api.id}.execute-api.us-east-1.amazonaws.com/prod/"
}

output "lambda_function_name" {
  value = aws_lambda_function.firehose_handler.function_name
}
