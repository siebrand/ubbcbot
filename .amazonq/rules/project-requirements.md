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

## Internationalization (i18n) Requirements
- All user-facing strings must use the current key-based i18n system
- Support English (en) and Dutch (nl) languages
- Translation files located in `src/translations/` directory
- Use descriptive keys following dot notation (e.g., `commands.help.description`)
- Never hardcode user-facing text in Python code
- Default language: Dutch (nl)
- Language detection based on Telegram user language preference
- Duplicate keys are not allowed in the json translation files
- Use `self._t(key, user_id, **params)` method in handlers for all user messages
- Translation keys must exist in both en.json and nl.json files
- Use parameter substitution for dynamic content: `{variable_name}`
- Language preference stored in customer database record
- Group messages must always use Dutch (nl) language code

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

A commit message must always be suggested right after completing changes to files in the project. 

## Business Logic
- Admin user ID: 15005473
- Supported box sizes: 1,2,6,8,10,12,15,16,18,20,24 units
- Test environment: all messages prefixed with "TEST - "
- Production environment: clean messages without prefixes
- Order cancellation: Admin-only with confirmation for full boxes
- Cancelled orders: Automatic inventory correction and customer notification
- Box status workflow: open → minimum_reached → full → ordered → delivered (during wholesale delivery)
- Offer completion: Only SOLD_OUT offers can be marked COMPLETED when all boxes are delivered
- Labeling completion: Updates orders to LABELING_COMPLETED status, checks for offer completion