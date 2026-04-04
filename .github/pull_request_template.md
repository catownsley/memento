# Pull Request

## Description


## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Security improvement
- [ ] Documentation update
- [ ] Dependency update

## Security Checklist

### Data Privacy
- [ ] No transcript data, PII, or conversation content in code or logs
- [ ] Anonymization layer tested with new changes
- [ ] No identifying information leaks through to Claude API calls
- [ ] Database queries use parameterized statements

### Authentication and Secrets
- [ ] No hardcoded credentials, API keys, or secrets in code
- [ ] API keys loaded from environment variables only
- [ ] .env.example updated if new config values added

### Dependencies
- [ ] No new dependencies without security review
- [ ] Dependencies scanned: `pip-audit -r requirements.txt`
- [ ] requirements.txt pinned to specific versions

### Error Handling
- [ ] No transcript content or PII in error messages
- [ ] Errors logged without sensitive data

### Input Validation
- [ ] File paths validated before reading
- [ ] Query inputs sanitized

## Testing
- [ ] Unit tests added or updated
- [ ] Tests pass locally: `pytest`
- [ ] Manual testing completed

## Documentation
- [ ] README.md updated if needed
- [ ] SECURITY.md updated if security related

## Related Issues

Closes #
Relates to #
