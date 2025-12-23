# UBBC Bot Project Requirements

## Project Context
This is a Telegram beer ordering bot built with AWS serverless architecture using SAM, Lambda, DynamoDB, and API Gateway.

## Code Standards
- Use Python 3.14 for all Lambda functions
- Follow AWS serverless best practices
- Maintain environment separation (test/prod)
- Use Parameter Store for sensitive configuration
- Follow resource naming convention: `ubbc-bot-{environment}-{resource-type}`
- Lambda functions must have CloudWatch logs with 7-day retention

## Security Requirements
- Never expose bot tokens in code or logs
- Use AWS Parameter Store for all secrets
- Implement proper IAM least privilege policies
- Validate all Telegram webhook inputs

## Deployment Standards
- All deployments must use SAM CLI
- Automatic webhook configuration during deployment
- Environment-specific configuration via Parameter Store
- Use managed S3 buckets for deployment artifacts

## Documentation Requirements
- Update README.md for any workflow changes
- Document all manual setup steps clearly
- Maintain clear separation between test and production instructions

## Commit Message Requirements
**CRITICAL**: Always provide conventional commit messages following this format:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `refactor:` for code refactoring
- `chore:` for maintenance tasks

Include:
- Clear, concise description of what changed
- Why the change was made (if not obvious)
- Any breaking changes or migration steps needed

Example:
```
feat: add automatic webhook setup in deployment script

- Retrieve bot token from Parameter Store during deployment
- Automatically configure Telegram webhook after infrastructure deployment
- Update README to reflect streamlined deployment process
- Eliminates manual webhook configuration step
```

## Business Logic
- Admin user ID: 15005473
- Supported box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- Test environment: all messages prefixed with "TEST - "
- Production environment: clean messages without prefixes