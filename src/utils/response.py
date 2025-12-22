import json
from typing import Dict, Any

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create standardized Lambda response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }