# Testing Guide for LLM Troubleshooting

## Quick Test Commands

### Run All Tests (as used in deploy.sh)
```bash
cd /Users/siebrand/Documents/repos/Kitano/UBBCBot
source test_env/bin/activate
python tests/run_tests.py
```

### Run Individual Test File
```bash
cd /Users/siebrand/Documents/repos/Kitano/UBBCBot
source test_env/bin/activate
python tests/test_translations.py
```

### Run Tests with Pytest (alternative)
```bash
cd /Users/siebrand/Documents/repos/Kitano/UBBCBot
source test_env/bin/activate
python -m pytest tests/test_translations.py -v
```

### Check Translation Duplicates
```bash
cd /Users/siebrand/Documents/repos/Kitano/UBBCBot
source test_env/bin/activate
python tests/find_duplicate_strings.py
```

## Test File Behavior

### tests/run_tests.py
- Runs each test file as a subprocess
- Captures stdout/stderr
- Returns exit code 0 for success, 1 for failure
- Each test file must be executable standalone

### tests/test_translations.py
- Checks for duplicate keys in JSON files
- Verifies key consistency between en.json and nl.json
- Validates placeholder consistency
- Tests language detection
- **Exit code 0 = all pass, 1 = any fail**

## Common Test Failures

### Translation Test Failures

**Duplicate Keys:**
```
❌ Found duplicate keys in en.json:
   - 'edit_contact' appears 2 times
```
**Fix:** Search for the key in the file and remove duplicate:
```bash
grep -n '"edit_contact"' src/translations/en.json
```

**Missing Keys:**
```
Missing in nl.json: {'new_key'}
```
**Fix:** Add the missing key to nl.json with Dutch translation

**Key Mismatch:**
```
Missing in en.json: {'extra_key'}
```
**Fix:** Remove the extra key from nl.json or add to en.json

## Debugging Failed Tests

### Step 1: Run the specific test file
```bash
source test_env/bin/activate
python tests/test_translations.py
```

### Step 2: Check the output
- Look for ❌ symbols indicating failures
- Read the error message carefully
- Note line numbers if provided

### Step 3: Fix the issue
- For duplicate keys: remove duplicates
- For missing keys: add to both files
- For placeholder issues: ensure {variable} names match

### Step 4: Verify fix
```bash
python tests/test_translations.py
```
Should show: `🎉 All translation tests passed!`

## Test Requirements

### Virtual Environment
All tests MUST run in the virtual environment:
```bash
source test_env/bin/activate
```

### Python Version
Tests use Python 3.14 from test_env

### Working Directory
Always run from project root:
```bash
cd /Users/siebrand/Documents/repos/Kitano/UBBCBot
```

## Integration with Deployment

The deploy.sh script runs:
```bash
python tests/run_tests.py
```

If this returns non-zero exit code, deployment is aborted.
