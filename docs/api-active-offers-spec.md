# API Specification: Get Active Offers

## Overview

Public REST API endpoint to retrieve all currently orderable offers with remaining capacity.

## Endpoint

```
GET https://{api-id}.execute-api.{region}.amazonaws.com/{environment}/offers
```

### Example URL

```
https://abc123def.execute-api.eu-west-1.amazonaws.com/prod/offers
```

## Authentication

None. This is a public, unauthenticated endpoint.

## Rate Limiting

API Gateway throttling applied at the stage level:
- **Burst limit**: 50 requests
- **Rate limit**: 10 requests/second

This prevents abuse while accommodating normal traffic patterns for a small community bot.

## Caching

- Cached response stored in DynamoDB (`counters` table) with key `counter_name = "offers_api_cache"`
- Cache item attributes:
  - `counter_name`: `"offers_api_cache"` (partition key)
  - `cached_response`: serialized JSON string of the response body
  - `expires_at`: Unix timestamp (epoch seconds) = creation time + 3600
- On invocation: read cache item from DynamoDB (1 read)
  - If valid (exists and `expires_at` > current time): return cached response immediately
  - If expired or missing: query offers + boxes, store serialized response in DynamoDB, return fresh result
- `Cache-Control: max-age=3600` response header allows caller-side caching
- Cost: negligible (a few DynamoDB reads/writes per day)

## Response

### Headers

```
Content-Type: application/json
Cache-Control: max-age=3600
Access-Control-Allow-Origin: *
```

### Success (200 OK)

```json
{
  "offers": [
    {
      "offer_id": 42,
      "name": "Tripel Karmeliet",
      "price_per_unit": "3.50",
      "description": "Belgian golden tripel, 8.4% ABV",
      "remaining_units": 7
    },
    {
      "offer_id": 45,
      "name": "Westmalle Dubbel",
      "price_per_unit": "2.80",
      "description": "",
      "remaining_units": 18
    }
  ],
  "cached_at": "2025-01-15T14:30:00Z"
}
```

`cached_at` reflects when the data was fetched from DynamoDB (not the request time). When serving a cached response, this value remains the original cache creation time.

### No Active Offers (200 OK)

```json
{
  "offers": [],
  "cached_at": "2025-01-15T14:30:00Z"
}
```

### Error (500)

```json
{
  "error": "internal_error"
}
```

## Business Logic

- **"Active" definition**: Only offers with status `ACTIVE` (i.e., published and not sold out, completed, or cancelled)
- **remaining_units**: Sum of `(max_capacity - current_quantity)` across all boxes where `current_quantity < max_capacity` for that offer
- **price_per_unit**: Returned as string to preserve decimal precision
- **Ordering**: Offers sorted by `offer_id` ascending (oldest first)

## Architecture Changes

### Infrastructure (template.yaml)

1. **New Lambda function**: `ubbc-bot-{environment}-offers-api`
   - Handler: `handlers.api.offers.handler`
   - CodeUri: `src/`
   - Runtime: Python 3.14
   - Architecture: arm64
   - Memory: 256 MB
   - Timeout: 10s
   - Read-only DynamoDB access to offers, boxes, and counters tables

2. **New API Gateway route** on existing `BotApi`:
   - Method: `GET`
   - Path: `/offers`
   - Integration: Lambda proxy
   - No API Gateway cache (avoids stage-level cache cluster cost)

3. **Update CORS** on `BotApi`:
   - Change `AllowMethods` from `"'POST'"` to `"'GET,POST'"`

4. **New CloudWatch Log Group**: `/aws/lambda/ubbc-bot-{environment}-offers-api` (7-day retention)

5. **IAM Policy** (least privilege):
   - `dynamodb:Scan` on `arn:aws:dynamodb:{region}:{account}:table/ubbc-bot-{environment}-offers`
   - `dynamodb:Query` on `arn:aws:dynamodb:{region}:{account}:table/ubbc-bot-{environment}-boxes/index/offer-index`
   - `dynamodb:GetItem` and `dynamodb:PutItem` on `arn:aws:dynamodb:{region}:{account}:table/ubbc-bot-{environment}-counters`

### Code Changes

1. **New directory**: `src/handlers/api/`
   - `src/handlers/api/__init__.py`
   - `src/handlers/api/offers.py` — Lambda handler for GET /offers

2. **Handler logic** (`src/handlers/api/offers.py`):
   - Check cache in counters table (`offers_api_cache` item)
   - If cache valid: return cached response with `Cache-Control` header
   - If cache miss: scan offers table with `FilterExpression` for `status = "active"`
   - For each active offer: query boxes table via `offer-index` GSI to compute remaining units
   - Build response, store in cache, return with `Cache-Control` header

3. **No changes** to existing webhook handler, bot logic, or DynamoDB table schemas

## Deployment

No additional manual steps. The new route deploys alongside the existing webhook endpoint via `sam deploy`.

## SAM Template Additions

### Log Group

```yaml
OffersApiLogGroup:
  Type: AWS::Logs::LogGroup
  Properties:
    LogGroupName: !Sub '/aws/lambda/ubbc-bot-${Environment}-offers-api'
    RetentionInDays: 7
    LogGroupClass: STANDARD
    Tags:
      - Key: Project
        Value: UBBCBot
      - Key: Environment
        Value: !Ref Environment
      - Key: Owner
        Value: siebrand
      - Key: CostCenter
        Value: personal
      - Key: Application
        Value: ubbc-telegram-bot
      - Key: ManagedBy
        Value: sam
```

### Lambda Function

```yaml
OffersApiHandler:
  Type: AWS::Serverless::Function
  DependsOn: OffersApiLogGroup
  Properties:
    FunctionName: !Sub 'ubbc-bot-${Environment}-offers-api'
    CodeUri: src/
    Handler: handlers.api.offers.handler
    Timeout: 10
    Events:
      GetOffers:
        Type: Api
        Properties:
          RestApiId: !Ref BotApi
          Path: /offers
          Method: get
    Policies:
      - Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Action:
              - dynamodb:Scan
            Resource: !GetAtt OffersTable.Arn
          - Effect: Allow
            Action:
              - dynamodb:Query
            Resource: !Sub '${BoxesTable.Arn}/index/offer-index'
          - Effect: Allow
            Action:
              - dynamodb:GetItem
              - dynamodb:PutItem
            Resource: !GetAtt CountersTable.Arn
    Tags:
      Project: UBBCBot
      Environment: !Ref Environment
      Owner: siebrand
      CostCenter: personal
      Application: ubbc-telegram-bot
      ManagedBy: sam
```

### CORS Update

```yaml
BotApi:
  Type: AWS::Serverless::Api
  Properties:
    # ...existing properties...
    Cors:
      AllowMethods: "'GET,POST'"  # Updated from "'POST'"
      AllowHeaders: "'Content-Type,X-Amz-Date,Authorization,X-Api-Key'"
      AllowOrigin: "'*'"
```

### Output

```yaml
OffersApiUrl:
  Description: Public API URL for active offers
  Value: !Sub 'https://${BotApi}.execute-api.${AWS::Region}.amazonaws.com/${Environment}/offers'
```
