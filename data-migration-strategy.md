# Data Migration Strategy

## Overview
This document outlines the data persistence and migration strategy for the UBBC Bot project to prevent data loss during deployments that require schema changes.

## Migration Types

### 1. Schema Changes Requiring Table Recreation
**Triggers:**
- Adding/removing DynamoDB table attributes with constraints
- Changing data types (e.g., float to Decimal)
- Modifying primary keys or indexes
- Changing table configuration (billing mode, etc.)

**Process:**
1. **Pre-deployment backup**
2. **Schema migration script execution**
3. **Data transformation and restoration**
4. **Validation and rollback capability**

### 2. Additive Changes (No Migration Required)
**Examples:**
- Adding new optional fields
- Adding new tables
- Adding new indexes (GSI/LSI)

## Migration Implementation

### Backup Strategy
```bash
# Create backup before deployment
./scripts/backup-data.sh <environment>

# Backup includes:
# - Full DynamoDB table exports
# - Schema definitions
# - Timestamp and version info
```

### Migration Scripts Location
```
/migrations/
├── v1.0.0-to-v1.1.0/
│   ├── backup.sh
│   ├── migrate.py
│   ├── validate.py
│   └── rollback.sh
└── v1.1.0-to-v1.2.0/
    ├── backup.sh
    ├── migrate.py
    ├── validate.py
    └── rollback.sh
```

### Enhanced Deployment Script
```bash
#!/bin/bash
# Enhanced deploy.sh with migration support

ENVIRONMENT=${1:-test}
CURRENT_VERSION=$(aws ssm get-parameter --name "/ubbc-bot/$ENVIRONMENT/version" --query 'Parameter.Value' --output text 2>/dev/null || echo "none")
NEW_VERSION=$(cat VERSION)

echo "🔍 Checking for required migrations..."
echo "Current version: $CURRENT_VERSION"
echo "Target version: $NEW_VERSION"

# Check if migration is required
if ./scripts/requires-migration.sh $CURRENT_VERSION $NEW_VERSION; then
    echo "⚠️  Migration required!"
    
    # Create backup
    echo "📦 Creating backup..."
    ./scripts/backup-data.sh $ENVIRONMENT
    
    # Run migration
    echo "🔄 Running migration..."
    ./migrations/$CURRENT_VERSION-to-$NEW_VERSION/migrate.py $ENVIRONMENT
    
    # Validate migration
    echo "✅ Validating migration..."
    ./migrations/$CURRENT_VERSION-to-$NEW_VERSION/validate.py $ENVIRONMENT
    
    if [ $? -ne 0 ]; then
        echo "❌ Migration validation failed! Rolling back..."
        ./migrations/$CURRENT_VERSION-to-$NEW_VERSION/rollback.sh $ENVIRONMENT
        exit 1
    fi
fi

# Continue with normal deployment
echo "🚀 Deploying application..."
sam build && sam deploy --config-env $ENVIRONMENT

# Update version
aws ssm put-parameter --name "/ubbc-bot/$ENVIRONMENT/version" --value "$NEW_VERSION" --overwrite
```

## Current Migration: v1.0.0 to v1.1.0

### Changes Required
1. **Customer table**: Add `authorization_status` field
2. **Offer table**: Change `price_per_unit` from float to Decimal
3. **Order table**: Change price fields from float to Decimal
4. **New table**: DiscountPeriod table

### Migration Steps
```python
# migrations/v1.0.0-to-v1.1.0/migrate.py
import boto3
from decimal import Decimal

def migrate_customer_table():
    # Add authorization_status field to existing customers
    # Default: "unauthorized" for existing users, "approved" for admin
    
def migrate_price_fields():
    # Convert float prices to Decimal in Offers and Orders tables
    
def create_discount_table():
    # Create new DiscountPeriod table
```

## Rollback Strategy

### Automatic Rollback Triggers
- Migration validation failure
- Deployment failure after migration
- Data integrity check failure

### Manual Rollback
```bash
./migrations/v1.0.0-to-v1.1.0/rollback.sh test
```

## Data Validation

### Pre-Migration Checks
- Verify backup completion
- Check data integrity
- Validate current schema

### Post-Migration Validation
- Data count verification
- Schema compliance check
- Functional testing
- Performance validation

## Environment-Specific Considerations

### Test Environment
- Allow destructive migrations for testing
- Faster migration with less validation
- Can recreate from scratch if needed

### Production Environment
- Zero-downtime migrations required
- Full backup and validation
- Gradual rollout capability
- Immediate rollback capability

## Monitoring and Alerts

### Migration Monitoring
- CloudWatch metrics for migration progress
- Alerts for migration failures
- Data integrity monitoring
- Performance impact tracking

### Success Criteria
- ✅ All data migrated successfully
- ✅ No data loss detected
- ✅ Application functionality verified
- ✅ Performance within acceptable limits

## Documentation Requirements

### Migration Documentation
Each migration must include:
- **MIGRATION.md**: Detailed migration steps
- **ROLLBACK.md**: Rollback procedures
- **VALIDATION.md**: Validation criteria
- **IMPACT.md**: Expected downtime and impact

### Deployment Notes
- Document breaking changes
- List required manual steps
- Specify rollback procedures
- Include validation commands

## Implementation Priority

### Phase 1: Basic Migration Framework
1. Create backup scripts
2. Implement version tracking
3. Add migration detection to deploy.sh

### Phase 2: Advanced Features
1. Zero-downtime migrations
2. Automated rollback
3. Performance monitoring
4. Cross-region backup

### Phase 3: Production Readiness
1. Blue-green deployments
2. Canary releases
3. Automated testing
4. Compliance reporting

## Current Action Required

For the immediate v1.1.0 deployment:

1. **Create backup script**:
```bash
./scripts/create-backup.sh test
```

2. **Manual migration** (one-time):
```bash
# Delete and recreate stack with new schema
aws cloudformation delete-stack --stack-name ubbc-bot-test
aws cloudformation wait stack-delete-complete --stack-name ubbc-bot-test
./deploy.sh test
```

3. **Implement migration framework** for future deployments

This ensures no future deployments will cause data loss and provides a clear path for production deployments.