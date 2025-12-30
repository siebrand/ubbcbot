# AWS Architecture Specification - Telegram Beer Ordering Bot

## 1. Architecture Overview

### 1.1 Design Principles
- **Serverless-first**: Minimize operational overhead and costs
- **Pay-per-use**: Scale to zero when inactive
- **Event-driven**
- **Cost-optimized**: Target monthly costs under $15 for typical usage

### 1.2 High-Level Architecture
```
Telegram API → API Gateway → Lambda Functions → DynamoDB
                    ↓
              EventBridge → SQS → Lambda (Scheduled Tasks)
                    ↓
                S3 + CloudFront (Images)
```

## 2. Core Services

### 2.1 Compute Layer
**AWS Lambda**
- **Purpose**: Bot logic, webhook processing, scheduled tasks
- **Runtime**: Python 3.14
- **Memory**: 512MB (adjustable based on performance)
- **Timeout**: 30 seconds for webhook handlers, 15 minutes for batch operations
- **Concurrency**: Reserved concurrency of 50 for webhook handlers

**Functions Structure**:
- `webhook-handler`: Process Telegram updates
- `offer-scheduler`: Publish scheduled offers
- `discount-manager`: Handle discount notifications
- `delivery-processor`: Process delivery notifications

### 2.2 API Layer
**Amazon API Gateway (REST API)**
- **Purpose**: Telegram webhook endpoint
- **Endpoint**: `/webhook` (POST)
- **Authentication**: API key validation
- **Throttling**: 100 requests/second
- **Integration**: Lambda proxy integration

### 2.3 Database Layer
**Amazon DynamoDB**
- **Billing Mode**: On-demand (pay-per-request)
- **Tables**:
  - `Offers`: Partition key: offer_id
  - `Orders`: Partition key: order_id, GSI: customer_id
  - `Customers`: Partition key: user_id
  - `Suppliers`: Partition key: supplier_id
  - `Groups`: Partition key: group_id
  - `Boxes`: Partition key: box_id, GSI: offer_id
  - `ScheduledTasks`: Partition key: task_id, GSI: execution_time

**Data Modeling**:
- Single-table design where applicable
- Global Secondary Indexes for query patterns
- TTL for temporary data (discount periods, scheduled tasks)

### 2.4 Storage Layer
**Amazon S3**
- **Purpose**: Image storage for beer offers
- **Bucket Structure**:
  - `offers/`: Main offer images
  - `options/`: Option-specific images (A, B, C)
  - `temp/`: Temporary uploads (24h TTL)
- **Lifecycle Policy**: Delete temp files after 1 day
- **Versioning**: Disabled to reduce costs

**Amazon CloudFront**
- **Purpose**: CDN for fast image delivery
- **Origin**: S3 bucket
- **Caching**: 24-hour TTL for images
- **Compression**: Automatic gzip compression

### 2.5 Messaging & Scheduling
**Amazon EventBridge**
- **Purpose**: Scheduled offer publishing, discount notifications
- **Rules**:
  - Offer publishing schedules
  - Discount expiry warnings
  - Daily cleanup tasks

**Amazon SQS**
- **Purpose**: Decouple batch operations
- **Queues**:
  - `delivery-notifications`: Process delivery messages
  - `discount-alerts`: Handle discount notifications
- **Configuration**: Standard queues with 14-day retention

## 3. Configuration & Monitoring

### 3.1 Configuration Management
**AWS Systems Manager Parameter Store**
- **Purpose**: Store configuration values
- **Parameters**:
  - `/ubbc-bot/telegram-token` (SecureString)
  - `/ubbc-bot/admin-user-id` (String): "15005473"
  - `/ubbc-bot/default-group-id` (String)
  - `/ubbc-bot/s3-bucket-name` (String)

**Lambda Environment Variables**:
- `DYNAMODB_TABLE_PREFIX`: Table name prefix
- `S3_BUCKET_NAME`: Image storage bucket
- `CLOUDFRONT_DOMAIN`: CDN domain for images

### 3.2 Monitoring & Logging
**Amazon CloudWatch**
- **Metrics**: Lambda duration, error rates, DynamoDB throttles
- **Logs**: Structured JSON logging from Lambda functions
- **Alarms**: Error rate > 5%, duration > 25 seconds
- **Dashboard**: Key metrics visualization

**AWS X-Ray** (Optional)
- **Purpose**: Distributed tracing for debugging
- **Sampling**: 10% of requests to minimize costs

## 4. Security

### 4.1 IAM Roles & Policies
**Lambda Execution Role**:
- DynamoDB: Read/Write access to bot tables
- S3: Read/Write access to image bucket
- SQS: Send/Receive messages
- EventBridge: Put events
- CloudWatch: Logs and metrics
- Parameter Store: Read configuration

### 4.2 API Security
- API Gateway API key for webhook endpoint
- Telegram webhook secret validation
- HTTPS-only communication

### 4.3 Data Protection
- DynamoDB encryption at rest (AWS managed keys)
- S3 bucket encryption (AES-256)
- Parameter Store SecureString for sensitive data

## 5. Deployment Strategy

### 5.1 Infrastructure as Code
**AWS SAM (Serverless Application Model)**
- `template.yaml`: Define all AWS resources
- `samconfig.toml`: Environment-specific configurations
- Automated deployment via AWS CLI

### 5.2 CI/CD Pipeline
**GitHub Actions** (or similar):
1. Code validation and testing
2. SAM build and package
3. Deploy to staging environment
4. Integration tests
5. Deploy to production

### 5.3 Environment Management
- **Development**: Local DynamoDB, reduced Lambda memory
- **Staging**: Full AWS stack with reduced capacity
- **Production**: Full capacity with monitoring

## 6. Cost Optimization

### 6.1 Estimated Monthly Costs (100 users, 1000 orders/month)
- **Lambda**: $2-5 (2M invocations)
- **DynamoDB**: $3-8 (on-demand pricing)
- **API Gateway**: $1-2 (REST API requests)
- **S3**: $1-3 (image storage)
- **CloudFront**: $1-2 (data transfer)
- **EventBridge**: $0 (free tier)
- **SQS**: $0 (free tier)
- **Total**: $8-20/month

### 6.2 Cost Control Measures
- DynamoDB on-demand billing (no idle costs)
- Lambda reserved concurrency to prevent runaway costs
- S3 lifecycle policies for cleanup
- CloudWatch log retention: 7 days
- Monitoring and alerting on cost anomalies

## 7. Scalability & Performance

### 7.1 Auto-Scaling
- **Lambda**: Automatic scaling up to 1000 concurrent executions
- **DynamoDB**: On-demand scaling for read/write capacity
- **API Gateway**: Built-in scaling

### 7.2 Performance Targets
- **Response Time**: < 2 seconds for order processing
- **Throughput**: 100 concurrent users
- **Availability**: 99.9% uptime

### 7.3 Performance Optimizations
- Lambda warm-up strategies
- DynamoDB single-table design
- CloudFront caching for images
- Efficient data serialization (JSON)

## 8. Disaster Recovery

Do not impement DR unless requested explicitly.

### 8.1 Backup Strategy
- **DynamoDB**: Point-in-time recovery enabled
- **S3**: Cross-region replication for critical images
- **Configuration**: Parameter Store values documented

### 8.2 Recovery Procedures
- Lambda functions: Redeploy from source code
- DynamoDB: Restore from point-in-time backup
- S3: Restore from cross-region replica
- Configuration: Restore from documentation

## 9. Development Guidelines

### 9.1 Code Structure
```
src/
├── handlers/           # Lambda function handlers
├── services/          # Business logic
├── models/            # Data models
├── utils/             # Utility functions
└── tests/             # Unit and integration tests
```

### 9.2 Dependencies
- `boto3`: AWS SDK
- `python-telegram-bot`: Telegram API wrapper
- `pydantic`: Data validation
- `pytest`: Testing framework

### 9.3 Local Development
- AWS SAM CLI for local testing
- DynamoDB Local for database
- LocalStack for full AWS simulation (optional)