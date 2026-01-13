# AWS Resource Naming and Tagging Standards

## Resource Naming Convention

### Standard Format
`ubbc-bot-{environment}-{resource-type}-{purpose}`

### Environment Values
- `test` - Testing environment
- `prod` - Production environment

### Resource Naming Examples

#### Lambda Functions
- `ubbc-bot-test-webhook-handler`
- `ubbc-bot-prod-webhook-handler`
- `ubbc-bot-test-offer-scheduler`
- `ubbc-bot-prod-discount-manager`

#### DynamoDB Tables
- `ubbc-bot-test-offers`
- `ubbc-bot-prod-offers`
- `ubbc-bot-test-customers`
- `ubbc-bot-prod-orders`

#### S3 Buckets
- `ubbc-bot-test-{account-id}-images`
- `ubbc-bot-prod-{account-id}-images`
- `ubbc-bot-test-{account-id}-documents`

#### API Gateway
- `ubbc-bot-test-api`
- `ubbc-bot-prod-api`

#### IAM Roles
- `ubbc-bot-test-lambda-execution-role`
- `ubbc-bot-prod-lambda-execution-role`
- `ubbc-bot-test-api-gateway-role`

#### CloudFront Distributions
- `ubbc-bot-test-cdn`
- `ubbc-bot-prod-cdn`

#### Parameter Store Parameters
- `/ubbc-bot/test/telegram-token`
- `/ubbc-bot/prod/telegram-token`
- `/ubbc-bot/test/admin-user-id`
- `/ubbc-bot/prod/default-group-id`

## Required Tags

### Mandatory Tags for All Resources
```yaml
Tags:
  Project: "UBBC-Bot"
  Environment: !Ref Environment  # test or prod
  Owner: "siebrand"
  CostCenter: "beer-ordering"
  Application: "telegram-bot"
  ManagedBy: "aws-sam"
  CreatedBy: "cloudformation"
  Purpose: !Sub "${AWS::StackName}-${ResourceType}"
```

### Additional Resource-Specific Tags

#### Lambda Functions
```yaml
Tags:
  Function: "webhook-handler"  # or specific function name
  Runtime: "python3.11"
  Timeout: "30"
```

#### DynamoDB Tables
```yaml
Tags:
  TableType: "transactional"  # or analytical
  BillingMode: "on-demand"
  BackupEnabled: "true"
```

#### S3 Buckets
```yaml
Tags:
  StorageClass: "standard"
  Versioning: "disabled"
  Encryption: "aes256"
```

## SAM Template Implementation

### Global Tags in template.yaml
```yaml
Globals:
  Function:
    Tags:
      Project: "UBBC-Bot"
      Environment: !Ref Environment
      Owner: "siebrand"
      CostCenter: "beer-ordering"
      Application: "telegram-bot"
      ManagedBy: "aws-sam"
      CreatedBy: "cloudformation"
```

### Resource-Specific Naming
```yaml
Resources:
  WebhookHandler:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub "ubbc-bot-${Environment}-webhook-handler"
      
  OffersTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: !Sub "ubbc-bot-${Environment}-offers"
      
  ImagesBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "ubbc-bot-${Environment}-${AWS::AccountId}-images"
      
  BotApi:
    Type: AWS::Serverless::Api
    Properties:
      Name: !Sub "ubbc-bot-${Environment}-api"
```

### samconfig.toml with Tags
```toml
[test.deploy.parameters]
stack_name = "ubbc-bot-test"
parameter_overrides = "Environment=test"
tags = "Project=UBBC-Bot Environment=test Owner=siebrand CostCenter=beer-ordering Application=telegram-bot ManagedBy=aws-sam"

[prod.deploy.parameters]
stack_name = "ubbc-bot-prod"
parameter_overrides = "Environment=prod"
tags = "Project=UBBC-Bot Environment=prod Owner=siebrand CostCenter=beer-ordering Application=telegram-bot ManagedBy=aws-sam"
```

## Cost Allocation Tags

### Primary Cost Tracking
- `CostCenter: "beer-ordering"` - For departmental cost allocation
- `Environment: "test|prod"` - For environment-based cost tracking
- `Project: "UBBC-Bot"` - For project-level cost analysis

### Secondary Cost Tracking
- `Owner: "siebrand"` - For ownership accountability
- `Application: "telegram-bot"` - For application-level costs
- `ManagedBy: "aws-sam"` - For infrastructure management costs

## Compliance and Governance

### Required for All Resources
- Consistent naming convention across all environments
- All mandatory tags applied to every resource
- Environment-specific parameter store paths
- Account ID inclusion in globally unique resource names

### Monitoring and Alerting
- CloudWatch alarms named: `ubbc-bot-{environment}-{metric}-alarm`
- Log groups named: `/aws/lambda/ubbc-bot-{environment}-{function}`
- SNS topics named: `ubbc-bot-{environment}-{purpose}-notifications`

### Security and Access
- IAM policies named: `ubbc-bot-{environment}-{service}-policy`
- Security groups named: `ubbc-bot-{environment}-{purpose}-sg`
- KMS keys aliased: `alias/ubbc-bot-{environment}-{purpose}`