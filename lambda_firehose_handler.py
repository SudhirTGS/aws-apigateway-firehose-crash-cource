import base64
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Firehose record transformation Lambda.

    Expects event in the Firehose transform format:
    { "records": [ {"recordId":"...","data":"BASE64"}, ... ] }

    Returns:
    { "records": [ {"recordId":"...","result":"Ok"|"ProcessingFailed","data":"BASE64"}, ... ] }
    """
    output = {"records": []}

    for record in event.get('records', []):
        record_id = record.get('recordId')
        try:
            raw = base64.b64decode(record.get('data', '')).decode('utf-8')
            obj = None
            try:
                obj = json.loads(raw)
            except Exception:
                # If not JSON, treat as a plain string payload
                obj = {"message": raw}

            # Simple transformation: mark and timestamp
            obj['transformed'] = True
            obj['_transformed_ts'] = int(time.time())

            transformed = json.dumps(obj)
            encoded = base64.b64encode(transformed.encode('utf-8')).decode('utf-8')

            output['records'].append({
                'recordId': record_id,
                'result': 'Ok',
                'data': encoded
            })
        except Exception as e:
            logger.exception('Failed to transform record %s: %s', record_id, str(e))
            # Return ProcessingFailed and include original data so Firehose can handle it
            output['records'].append({
                'recordId': record_id,
                'result': 'ProcessingFailed',
                'data': record.get('data')
            })

    return output
